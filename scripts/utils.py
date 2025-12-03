import os
import sys
import base64
import json
from typing import List, Dict, Optional
import time
import requests

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


# ======================================================================================
# Exceptions
# ======================================================================================

class FabricAuthError(Exception):
    pass

class FabricApiError(Exception):
    pass


# ======================================================================================
# Authentication
# ======================================================================================

def _get_env_or_fail(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise FabricAuthError(f"Missing environment variable: {name}")
    return value


def get_access_token_spn() -> str:
    tenant_id = _get_env_or_fail("FABRIC_TENANT_ID")
    client_id = _get_env_or_fail("FABRIC_CLIENT_ID")
    client_secret = _get_env_or_fail("FABRIC_CLIENT_SECRET")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://api.fabric.microsoft.com/.default",
    }

    resp = requests.post(token_url, data=data)

    if resp.status_code != 200:
        raise FabricAuthError(
            f"Failed to acquire token. HTTP {resp.status_code}: {resp.text}"
        )

    token = resp.json().get("access_token")
    if not token:
        raise FabricAuthError("Token response missing 'access_token'.")

    return token


# ======================================================================================
# API Wrapper
# ======================================================================================

def fabric_request(method: str, path: str, token: str, **kwargs) -> requests.Response:
    url = f"{FABRIC_API_BASE}/{path.lstrip('/')}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"

    if "json" in kwargs and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    print(f"Calling Fabric API: {method} {url}")
    resp = requests.request(method, url, headers=headers, **kwargs)

    # We do NOT raise for 202; only for 4xx or 5xx
    if resp.status_code >= 400:
        raise FabricApiError(
            f"{method} {url} failed. HTTP {resp.status_code}: {resp.text}"
        )

    return resp


# ======================================================================================
# Workspace Management
# ======================================================================================

def get_or_create_workspace(workspace_name: str, token: str, capacity_id: Optional[str] = None) -> str:

    resp = fabric_request("GET", "workspaces", token)
    data = resp.json()
    workspaces = data.get("value", data.get("workspaces", []))

    for ws in workspaces:
        if ws.get("displayName") == workspace_name:
            print(f"Workspace '{workspace_name}' already exists (id={ws['id']}).")
            return ws["id"]

    body = {"displayName": workspace_name}
    if capacity_id:
        body["capacityId"] = capacity_id

    print(f"Creating workspace '{workspace_name}'...")
    resp = fabric_request("POST", "workspaces", token, json=body)
    ws = resp.json()

    print(f"Workspace created (id={ws['id']}).")
    return ws["id"]


# ======================================================================================
# Helpers
# ======================================================================================

def list_items_by_type(workspace_id: str, item_type: str, token: str) -> List[Dict]:
    path = f"workspaces/{workspace_id}/items?type={item_type}"
    resp = fabric_request("GET", path, token)
    data = resp.json()
    return data.get("value", data.get("items", []))


def build_definition_parts_from_folder(folder: str) -> List[Dict[str, str]]:
    parts = []

    for root, _, files in os.walk(folder):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, folder).replace("\\", "/")

            with open(full_path, "rb") as f:
                content = f.read()

            parts.append({
                "path": rel_path,
                "payload": base64.b64encode(content).decode("ascii"),
                "payloadType": "InlineBase64",
            })

    if not parts:
        raise ValueError(f"No files found in PBIP folder: {folder}")

    return parts


# ======================================================================================
# ITEM CREATION / UPDATE
# ======================================================================================

def create_or_update_item_from_folder(workspace_id: str, folder: str, item_type: str, token: str) -> str:
    display_name = os.path.basename(folder).split(".", 1)[0]

    print(f"\n=== Publishing {item_type} from folder: {folder}")
    print(f"Item displayName = {display_name}")

    parts = build_definition_parts_from_folder(folder)
    definition = {"parts": parts}

    existing = None
    for it in list_items_by_type(workspace_id, item_type, token):
        if it.get("displayName") == display_name:
            existing = it
            break

    # ------------------------------------------------------------------------------
    # CASE 1 : CREATE NEW ITEM
    # ------------------------------------------------------------------------------

    if existing is None:
        print(f"🆕 Creating new {item_type} '{display_name}'")

        body = {
            "displayName": display_name,
            "type": item_type,
            "definition": definition,
        }

        resp = fabric_request(
            "POST",
            f"workspaces/{workspace_id}/items",
            token,
            json=body,
        )

        # NEW LOGIC : HANDLE 202 WITH POLLING
        status = resp.status_code

        if status == 201:
            # Success normal
            item = resp.json()
            print(f"✅ Created {item_type} '{display_name}' (id={item['id']})")
            return item["id"]

        if status == 202:
            print("⏳ Item creation accepted (202). Polling every 3 seconds until creation is complete...")

            item_id = None
            retries = 0
            max_retries = 40  # = 2 minutes max

            while retries < max_retries:
                items = list_items_by_type(workspace_id, item_type, token)

                for it in items:
                    if it.get("displayName") == display_name:
                        item_id = it["id"]
                        print(f"🎉 Successfully detected created item: {item_id}")
                        return item_id

                retries += 1
                time.sleep(3)

            raise FabricApiError(f"Timeout: Item '{display_name}' did not appear after 2 minutes.")

        # Any other status but not 201/202
        print("\n❌ FABRIC DID NOT RETURN A VALID ITEM ON CREATION")
        print("Raw response:")
        print(resp.text)
        raise FabricApiError(f"Fabric failed to create {item_type} '{display_name}'.")

    # ------------------------------------------------------------------------------
    # CASE 2 : UPDATE EXISTING ITEM
    # ------------------------------------------------------------------------------

    item_id = existing["id"]
    print(f"🔄 Updating existing {item_type} '{display_name}' (id={item_id})")

    body = {"definition": definition}

    resp = fabric_request(
        "POST",
        f"workspaces/{workspace_id}/items/{item_id}/updateDefinition?updateMetadata=false",
        token,
        json=body,
    )

    try:
        json_resp = resp.json()
    except Exception:
        json_resp = None

    if json_resp is None:
        print("⚠️ WARNING: Fabric returned NO JSON for update.")
        print("Raw response:")
        print(resp.text)
        print("Continuing...")

    print(f"✅ Updated {item_type} '{display_name}' (id={item_id})")
    return item_id
