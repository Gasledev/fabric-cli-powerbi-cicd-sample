import os
import json
import time
import requests

FABRIC_API = "https://api.fabric.microsoft.com/v1"


# =====================================================================
# AUTHENTICATION
# =====================================================================

def fabric_post_token():
    """
    Authenticate using Service Principal via OAuth2 client_credentials
    and return access token.
    """
    tenant = os.environ.get("FABRIC_TENANT_ID")
    client_id = os.environ.get("FABRIC_CLIENT_ID")
    client_secret = os.environ.get("FABRIC_CLIENT_SECRET")

    print("Authenticating with Service Principal (client_credentials)...")

    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://api.fabric.microsoft.com/.default"
    }

    resp = requests.post(url, data=data)

    if resp.status_code != 200:
        raise Exception(
            f"❌ AUTH ERROR: {resp.status_code}\n{resp.text}"
        )

    token = resp.json().get("access_token")
    print("✅ SPN authentication successful.")
    return token


# =====================================================================
# GENERIC FABRIC REQUEST WRAPPER
# =====================================================================

def fabric_request(method, endpoint, **kwargs):
    """
    Wrapper around Fabric REST API with auth and error handling.
    Always prints raw error if API returns unexpected response.
    """

    token = fabric_post_token()  # Always fetch fresh token
    url = FABRIC_API + endpoint

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"

    resp = requests.request(method, url, headers=headers, **kwargs)

    if not (200 <= resp.status_code < 300):
        print("❌ FABRIC API ERROR")
        print("URL:", url)
        print("Status:", resp.status_code)
        print("Headers:", resp.headers)
        print("Body:", resp.text)
        raise FabricApiError(
            f"{method} {url} failed. HTTP {resp.status_code}: {resp.text}"
        )

    return resp


# =====================================================================
# CUSTOM EXCEPTION TYPE
# =====================================================================

class FabricApiError(Exception):
    pass


# =====================================================================
# WORKSPACE MANAGEMENT
# =====================================================================

def create_workspace(workspace_name, capacity_name, admin_upns):
    """
    Create or retrieve Fabric workspace ID by name.
    """

    print(f"Calling Fabric API: GET {FABRIC_API}/workspaces")
    resp = fabric_request("GET", "/workspaces")
    workspaces = resp.json()

    # Already exists?
    for ws in workspaces:
        if ws["displayName"] == workspace_name:
            print(f"Workspace '{workspace_name}' already exists (id={ws['id']}).")
            return ws["id"]

    # Create workspace
    print(f"Creating workspace '{workspace_name}'...")
    body = {"displayName": workspace_name}

    resp = fabric_request("POST", "/workspaces", json=body)
    new_ws = resp.json()
    print(f"Workspace created (id={new_ws['id']}).")

    return new_ws["id"]


# =====================================================================
# ITEM CREATION / UPDATE (SEMANTIC MODEL / REPORT)
# =====================================================================

def create_or_update_item_from_folder(workspace_id, folder_path, item_type):
    display_name = os.path.basename(folder_path).split(".")[0]
    print(f"=== Publishing {item_type} from folder: {folder_path}")
    print(f"Item displayName = {display_name}")

    # Check definition folder
    definition_path = os.path.join(folder_path, "definition")
    if not os.path.exists(definition_path):
        raise FabricApiError(f"❌ Definition folder missing: {definition_path}")

    # Fetch existing items
    print(f"Calling Fabric API: GET {FABRIC_API}/workspaces/{workspace_id}/items?type={item_type}")
    resp = fabric_request(
        "GET",
        f"/workspaces/{workspace_id}/items?type={item_type}"
    )

    existing = None
    try:
        items = resp.json() or []
        for it in items:
            if it.get("displayName") == display_name:
                existing = it
                break
    except Exception as ex:
        print("❌ ERROR reading existing items:", ex)
        print("Raw GET response:", resp.text)

    # =====================================================================
    # UPDATE EXISTING ITEM
    # =====================================================================

    if existing:
        item_id = existing["id"]
        print(f"🔄 Updating existing {item_type} '{display_name}' (id={item_id})")

        print(f"Calling Fabric API: POST /items/{item_id}/updateDefinition")

        files = {
            "definition": open(os.path.join(folder_path, "definition.pbir"), "rb")
        }

        resp = fabric_request(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/updateDefinition?updateMetadata=false",
            files=files
        )

        # Handle null response
        try:
            json_resp = resp.json()
        except:
            json_resp = None

        if not json_resp:
            print("⚠️ WARNING: Fabric returned NO JSON for update.")
            print("HTTP status:", resp.status_code)
            print("Headers:", resp.headers)
            print("Raw response:")
            print(resp.text)
            print("Continuing anyway...")
            return

        print(f"✅ Updated {item_type} '{display_name}'")
        return

    # =====================================================================
    # CREATE NEW ITEM
    # =====================================================================

    print(f"🆕 Creating new {item_type} '{display_name}'")
    print(f"Calling Fabric API: POST /items")

    files = {
        "item": open(os.path.join(folder_path, "item.json"), "rb"),
        "definition": open(os.path.join(folder_path, "definition.pbir"), "rb")
    }

    resp = fabric_request(
        "POST",
        f"/workspaces/{workspace_id}/items",
        files=files
    )

    # Detect null response
    try:
        item = resp.json()
    except:
        item = None

    if not item or "id" not in item:
        print("❌ FABRIC DID NOT RETURN A VALID ITEM ON CREATION")
        print("HTTP status:", resp.status_code)
        print("Headers:", resp.headers)
        print("Raw response:")
        print(resp.text)
        raise FabricApiError(f"Fabric failed to create {item_type} '{display_name}'.")

    print(f"🎉 Created {item_type} '{display_name}' (id={item['id']})")


# =====================================================================
# END OF FILE
# =====================================================================
