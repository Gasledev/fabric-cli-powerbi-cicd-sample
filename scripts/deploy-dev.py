import os
import argparse
from utils import *

parser = argparse.ArgumentParser()
parser.add_argument("--spn-auth", action="store_true", default=True)
parser.add_argument("--workspace", default="DevWorkspace")
parser.add_argument("--admin-upns", default=os.getenv("FABRIC_ADMIN_UPNS"))
parser.add_argument("--capacity", default=os.getenv("FABRIC_CAPACITY"))

args = parser.parse_args()

workspace = args.workspace
capacity = args.capacity
admin_upns = args.admin_upns

print("=== 🚀 DEPLOY TO DEV ===")

# 1) Authenticate
if args.spn_auth:
    fab_authenticate_spn()

# 2) Ensure workspace exists
workspace_id = create_workspace(workspace, capacity, upns=[admin_upns])

# 3) Deploy Semantic Model
print("📦 Deploying Semantic Model...")
deploy_item(
    "src/CleanModel.SemanticModel",
    workspace_name=workspace
)

# 4) Deploy Report
print("📊 Deploying Report...")
deploy_item(
    "src/CleanReport.Report",
    workspace_name=workspace
)

print("✅ Deployment to DEV completed successfully.")
