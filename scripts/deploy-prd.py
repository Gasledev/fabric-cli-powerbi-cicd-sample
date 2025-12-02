import argparse
from utils import fab_authenticate_spn, create_workspace, deploy_item

parser = argparse.ArgumentParser()
parser.add_argument("--spn-auth", action="store_true", default=True)
parser.add_argument("--workspace", default="ProdWorkspace")
parser.add_argument("--capacity", default=None)
parser.add_argument("--admin-upns", default=None)
args = parser.parse_args()

print("=== 🚀 DEPLOY TO PROD ===")

# Authenticate
fab_authenticate_spn()

# Create or get workspace
ws_id = create_workspace(args.workspace, args.capacity, args.admin_upns)

# Deploy Semantic Model
deploy_item("src/CleanModel.SemanticModel", args.workspace)

# Deploy Report
deploy_item("src/CleanReport.Report", args.workspace)

print("🎉 PROD deployment complete!")
