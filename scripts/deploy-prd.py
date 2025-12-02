import argparse
import glob
import os

from utils import (
    get_access_token_spn,
    get_or_create_workspace,
    create_or_update_item_from_folder,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy PBIP Report & SemanticModel to PROD workspace using Fabric REST APIs."
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Fabric workspace name (PROD)",
    )
    parser.add_argument(
        "--capacity",
        default="",
        help="(Optional) Capacity ID to assign the workspace to.",
    )
    parser.add_argument(
        "--admin-upns",
        default="",
        help="(Unused for now) Admin UPNs – kept for compatibility.",
    )

    args = parser.parse_args()

    print("=== 🚀 DEPLOY TO PROD ===")

    # 1. Auth SPN -> token
    print("Authenticating with Service Principal (client_credentials)...")
    token = get_access_token_spn()
    print("✅ SPN authentication successful.")

    # 2. Workspace PROD
    ws_id = get_or_create_workspace(
        workspace_name=args.workspace,
        token=token,
        capacity_id=args.capacity or None,
    )
    print(f"Using workspace '{args.workspace}' (id={ws_id})")

    # 3. Deploy Semantic Models (*.SemanticModel in src/)
    semantic_folders = glob.glob(os.path.join("src", "*.SemanticModel"))
    if not semantic_folders:
        print("No *.SemanticModel folders found under src/ – skipping semantic models.")
    else:
        for folder in semantic_folders:
            create_or_update_item_from_folder(
                workspace_id=ws_id,
                folder=folder,
                item_type="SemanticModel",
                token=token,
            )

    # 4. Deploy Reports (*.Report in src/)
    report_folders = glob.glob(os.path.join("src", "*.Report"))
    if not report_folders:
        print("No *.Report folders found under src/ – skipping reports.")
    else:
        for folder in report_folders:
            create_or_update_item_from_folder(
                workspace_id=ws_id,
                folder=folder,
                item_type="Report",
                token=token,
            )

    print("\n🎉 PROD deployment finished successfully.")


if __name__ == "__main__":
    main()
