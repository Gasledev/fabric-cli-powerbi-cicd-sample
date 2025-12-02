import os
import subprocess
import shutil
import json
import uuid


# -----------------------------------------------------------
# 🔧 Run a Fabric CLI command
# -----------------------------------------------------------
def run_fab_command(cmd):
    """Run a Fabric CLI command and fail on error."""
    print(f"Running FAB command: fab {cmd}")

    process = subprocess.run(
        ["fab"] + cmd.split(),
        text=True,
        capture_output=True
    )

    if process.returncode != 0:
        raise Exception(
            f"Error running fab command.\n"
            f"Exit code: {process.returncode}\n"
            f"Stdout:\n{process.stdout}\n"
            f"Stderr:\n{process.stderr}"
        )

    return process.stdout


# -----------------------------------------------------------
# 🔐 Authenticate with Service Principal (OFFICIAL SYNTAX)
# -----------------------------------------------------------
def fab_authenticate_spn():
    print("Authenticating with SPN...")

    client_id = os.getenv("FABRIC_CLIENT_ID")
    client_secret = os.getenv("FABRIC_CLIENT_SECRET")
    tenant_id = os.getenv("FABRIC_TENANT_ID")

    if not client_id or not client_secret or not tenant_id:
        raise Exception("Missing Fabric SPN environment variables.")

    # OFFICIAL SPN LOGIN SYNTAX (from Microsoft)
    run_fab_command(
        f"auth login -u {client_id} -p {client_secret} --tenant {tenant_id}"
    )

    print("SPN authentication successful.")


# -----------------------------------------------------------
# 🏢 Create or retrieve workspace
# -----------------------------------------------------------
def create_workspace(workspace_name, capacity=None, upns=None):
    print(f"Ensuring workspace exists: {workspace_name}")

    raw = run_fab_command("workspace list --output json")
    workspaces = json.loads(raw)

    for ws in workspaces:
        if ws["displayName"] == workspace_name:
            print(f"Workspace already exists → {ws['id']}")
            return ws["id"]

    cmd = f"workspace create --display-name \"{workspace_name}\""
    if capacity:
        cmd += f" --capacity {capacity}"

    ws_data = json.loads(run_fab_command(cmd))
    ws_id = ws_data["id"]

    print(f"Workspace created → {ws_id}")

    if upns:
        for u in upns.split(","):
            run_fab_command(
                f"workspace user assign --workspace-id {ws_id} --user {u} --role Admin"
            )

    return ws_id


# -----------------------------------------------------------
# 📦 Deploy PBIP items (semantic model or report)
# -----------------------------------------------------------
def deploy_item(src_folder, workspace_name):
    print(f"Deploying PBIP item → {src_folder}")

    if not os.path.isdir(src_folder):
        raise Exception(f"PBIP folder not found: {src_folder}")

    staging = f"_stg/{uuid.uuid4()}"
    os.makedirs(staging, exist_ok=True)

    dest = f"{staging}/{os.path.basename(src_folder)}"
    shutil.copytree(src_folder, dest)

    result = run_fab_command(
        f"item import --workspace \"{workspace_name}\" --path \"{dest}\""
    )

    print(result)
    return result
