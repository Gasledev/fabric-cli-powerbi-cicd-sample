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
# 🔐 Authenticate with Service Principal (SPN)
# -----------------------------------------------------------
def fab_authenticate_spn():
    print("Authenticating with SPN...")

    # Verify env vars exist
    if not os.getenv("FABRIC_CLIENT_ID") or not os.getenv("FABRIC_CLIENT_SECRET") or not os.getenv("FABRIC_TENANT_ID"):
        raise Exception("Missing Fabric SPN environment variables.")

    # ✔ CORRECT COMMAND FOR YOUR FABRIC CLI VERSION
    # Login WITHOUT passing any arguments
    run_fab_command("auth login")

    print("SPN authentication successful.")



# -----------------------------------------------------------
# 🏢 Create workspace (idempotent)
# -----------------------------------------------------------
def create_workspace(workspace_name, capacity=None, upns=None):
    """Create a workspace or return its ID if it already exists."""
    print(f"Ensuring workspace exists: {workspace_name}")

    # List existing workspaces
    json_out = run_fab_command("workspace list --output json")
    workspaces = json.loads(json_out)

    # Return existing workspace
    for ws in workspaces:
        if ws["displayName"] == workspace_name:
            print(f"Workspace already exists: {ws['id']}")
            return ws["id"]

    # Create workspace
    cmd = f"workspace create --display-name \"{workspace_name}\""

    if capacity:
        cmd += f" --capacity {capacity}"

    ws_data = json.loads(run_fab_command(cmd))

    ws_id = ws_data["id"]
    print(f"Workspace created → ID = {ws_id}")

    # Assign admin users
    if upns:
        for u in upns:
            run_fab_command(
                f"workspace user assign --workspace-id {ws_id} "
                f"--user {u} --role Admin"
            )

    return ws_id


# -----------------------------------------------------------
# 📦 Deploy a PBIP item (Report or Semantic Model)
# -----------------------------------------------------------
def deploy_item(src_folder, workspace_name):
    """Deploy any PBIP folder (Report or Semantic Model) to Fabric."""
    print(f"Deploying item → {src_folder}")

    if not os.path.isdir(src_folder):
        raise Exception(f"Path not found: {src_folder}")

    # Temporary staging path
    staging = f"_stg/{uuid.uuid4()}"
    os.makedirs(staging, exist_ok=True)

    # Copy PBIP into staging
    final_path = f"{staging}/{os.path.basename(src_folder)}"
    shutil.copytree(src_folder, final_path)

    # Import item into Fabric
    output = run_fab_command(
        f"item import "
        f"--workspace \"{workspace_name}\" "
        f"--path \"{final_path}\""
    )

    print("Deployment result:")
    print(output)

    return output
