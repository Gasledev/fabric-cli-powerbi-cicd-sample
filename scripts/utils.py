import os
import sys
import base64
import json
from typing import List, Dict, Optional

import requests

# Base Fabric REST API
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


class FabricAuthError(Exception):
    """Authentication/Token errors."""
    pass


class FabricApiError(Exception):
    """Fabric REST API call errors."""
    pass


def _get_env_or_fail(name: str) -> str:
    """Get an env var or raise a clear error."""
    value = os.getenv(name)
    if not value:
        raise FabricAuthError(f"Missing environment variable: {name}")
    return value


def get_access_token_spn() -> str:
    """
    Récupère un access token Microsoft Entra pour Fabric en client_credentials
    (Service Principal) vers le scope Fabric: https://api.fabric.microsoft.com/.default
    """
    tenant_id = _get_env_or_fail("FABRIC_TENANT_ID")
    client_id = _get_env_or_fail("FABRIC_CLIENT_ID")
    client_secret = _get_env_or_fail("FABRIC_CLIENT_SECRET")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        # Scope générique pour les APIs Fabric en client credentials
        # cf. discussions communautaires :contentReference[oaicite:1]{index=1}
        "scope": "https://api.fabric.microsoft.com/.default",
    }

    resp = requests.post(token_url, data=data)
    if resp.status_code != 200:
        raise FabricAuthError(
            f"Failed to acquire token. HTTP {resp.status_code}: {resp.text}"
        )

    token = resp.json().get("access_token")
    if not token:
        raise FabricAuthError("Token response does not contain 'access_token'.")
    return token


def fabric_request(method: str, path: str, token: str, **kwargs) -> requests.Response:
    """
    Appelle l’API Fabric REST (Core) :
      - Ajoute automatiquement le header Authorization: Bearer <token>
      - Lève une exception si le status HTTP n’est pas 2xx
    """
    url = f"{FABRIC_API_BASE}/{path.lstrip('/')}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"

    # Si on envoie un body, on s’assure du content-type JSON
    if "json" in kwargs and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    print(f"Calling Fabric API: {method} {url}")
    resp = requests.request(method, url, headers=headers, **kwargs)

    if not resp.ok:
        raise FabricApiError(
            f"{method} {url} failed. "
            f"HTTP {resp.status_code}: {resp.text}"
        )

    return resp


def get_or_create_workspace(
    workspace_name: str,
    token: str,
    capacity_id: Optional[str] = None,
) -> str:
    """
    1. Liste les workspaces (GET /workspaces) :contentReference[oaicite:2]{index=2}
    2. Si un workspace avec displayName == workspace_name existe -> retourne son id
    3. Sinon, crée le workspace (POST /workspaces) :contentReference[oaicite:3]{index=3}
    """
    # 1. List workspaces
    resp = fabric_request("GET", "workspaces", token)
    data = resp.json()

    # Selon la doc Fabric, les collections sont typiquement dans 'value'
    workspaces = data.get("value", data.get("workspaces", []))

    for ws in workspaces:
        if ws.get("displayName") == workspace_name:
            ws_id = ws.get("id")
            print(f"Workspace '{workspace_name}' already exists (id={ws_id}).")
            return ws_id

    # 2. Create workspace
    body: Dict[str, object] = {"displayName": workspace_name}
    if capacity_id:
        body["capacityId"] = capacity_id

    print(f"Creating workspace '{workspace_name}'...")
    resp = fabric_request("POST", "workspaces", token, json=body)
    ws = resp.json()
    ws_id = ws["id"]
    print(f"Workspace created (id={ws_id}).")
    return ws_id


def list_items_by_type(
    workspace_id: str,
    item_type: str,
    token: str,
) -> List[Dict]:
    """
    Liste les items d’un workspace filtrés par type (Report, SemanticModel, ...) :contentReference[oaicite:4]{index=4}
      GET /workspaces/{workspaceId}/items?type={item_type}
    """
    path = f"workspaces/{workspace_id}/items?type={item_type}"
    resp = fabric_request("GET", path, token)
    data = resp.json()
    return data.get("value", data.get("items", []))


def build_definition_parts_from_folder(folder: str) -> List[Dict[str, str]]:
    """
    Construit la liste des 'parts' pour un Item Definition à partir d'un dossier PBIP :
      - parcourt tous les fichiers (definition/, StaticResources/, .platform, etc.)
      - crée un part par fichier:
          path       = chemin relatif (style 'definition/report.json')
          payload    = fichier encodé en base64
          payloadType= InlineBase64 (unique valeur supportée) :contentReference[oaicite:5]{index=5}
    """
    parts: List[Dict[str, str]] = []

    for root, _, files in os.walk(folder):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, folder).replace("\\", "/")

            with open(full_path, "rb") as f:
                content = f.read()

            b64 = base64.b64encode(content).decode("ascii")
            parts.append(
                {
                    "path": rel_path,
                    "payload": b64,
                    "payloadType": "InlineBase64",
                }
            )

    if not parts:
        raise ValueError(f"No files found in PBIP folder: {folder}")

    return parts


def create_or_update_item_from_folder(
    workspace_id: str,
    folder: str,
    item_type: str,
    token: str,
) -> str:
    """
    Crée ou met à jour un item (Report ou SemanticModel) dans Fabric à partir d’un
    dossier PBIP (.Report ou .SemanticModel) en utilisant Create Item / Update Definition :contentReference[oaicite:6]{index=6}

    - displayName = nom du dossier sans l’extension (.Report ou .SemanticModel)
    - On check si un item de ce type existe déjà dans le workspace:
        - NON -> POST /workspaces/{ws}/items
        - OUI -> POST /workspaces/{ws}/items/{itemId}/updateDefinition?updateMetadata=true
    """
    display_name = os.path.basename(folder)
    # Exemple: "pbi_test.Report" -> "pbi_test"
    if "." in display_name:
        display_name = display_name.split(".", 1)[0]

    print(f"\n=== Publishing {item_type} from folder: {folder}")
    print(f"Item displayName = {display_name}")

    parts = build_definition_parts_from_folder(folder)
    definition = {"parts": parts}

    # Recherche d’un item existant de ce type + nom
    existing_items = list_items_by_type(workspace_id, item_type, token)
    item_id: Optional[str] = None
    for it in existing_items:
        if it.get("displayName") == display_name:
            item_id = it.get("id")
            break

    if item_id is None:
        # Création
        body = {
            "displayName": display_name,
            "type": item_type,  # "Report" ou "SemanticModel"
            "definition": definition,
        }
        resp = fabric_request(
            "POST",
            f"workspaces/{workspace_id}/items",
            token,
            json=body,
        )
        item = None
        try:
            item = resp.json()
        except Exception:
            item = None
        
        # Vérification stricte : item doit exister ET contenir un id
        if not item or "id" not in item:
            print("\n❌ ERROR: Fabric API did not return a valid item after creation.")
            print("➡ This means the PBIP structure is invalid or incomplete.")
            print("➡ Here is the RAW response from Fabric:")
            print("----------------------------------------")
            print(resp.text)
            print("----------------------------------------")
            raise FabricApiError(
                f"Fabric failed to create item '{display_name}' of type '{item_type}'."
            )
        
        item_id = item["id"]
        print(f"✅ Created {item_type} '{display_name}' (id={item_id})")

    else:
        # Update du Definition (et metadata via .platform si présent)
        body = {
            "definition": definition,
        }
        item = resp.json()
        item_id = item["id"]
        print(...)

        print(f"✅ Updated {item_type} '{display_name}' (id={item_id})")

    return item_id
