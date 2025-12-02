import os
import argparse
from utils import *

parser = argparse.ArgumentParser()
parser.add_argument("--spn-auth", action="store_true", default=True)
parser.add_argument("--workspace", default="ProdWorkspace")
parser.add_argument("--admin-upns", default=os.getenv("FABRIC_ADMIN_UPNS"))
parser.add_argument("--capacity", default=os.getenv("FABRIC_CAPACITY"))

args = parser.parse_args()

workspace = args.workspace
capacity = args.capacity
admin_upns = args.admin_upns

# Auth
if args.spn_auth:
    fab_authenticate_spn()

# Create workspace
workspace_id = create_workspace(workspace, capacity, upns=[admin_upns])

# Deploy semantic model
semantic_id = deploy_item(
    "src/CleanModel.SemanticModel",
    workspace_name=workspace
)

# Deploy report
deploy_item(
    "src/CleanReport.Report",
    workspace_name=workspace
)

print("Deployment to PROD completed successfully.")
