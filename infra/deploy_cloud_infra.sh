#!/usr/bin/env bash

# Fail on error
set -e

# Change directory to the infra folder (where the script is located)
cd "$(dirname "$0")"

echo "==============================================="
echo "  Deploying GCP Infrastructure via Terraform   "
echo "==============================================="

# 1. Load shared configuration
source ./common.sh
STATE_BUCKET=$(python3 -c "import json; print(json.load(open('variables.tfvars.json'))['state_bucket_name'])")
REGION=$(python3 -c "import json; print(json.load(open('variables.tfvars.json')).get('region', 'europe-west1'))")
ADMIN_GROUP_EMAIL=$(python3 -c "import json; print(json.load(open('variables.tfvars.json')).get('admin_group_email', ''))")

echo "Project ID: $PROJECT_ID"
echo "State Bucket: $STATE_BUCKET"
echo "Region: $REGION"
echo "Admin Group Email: $ADMIN_GROUP_EMAIL"

# 3. Execute Part 2 (Remote state storage, Datastore, and Service Account permissions)
echo -e "\n--- Step 2: Deploying Main Resources (Part 2) ---"
cd cloud
# Initialize with GCS remote state configuration pointing to the bucket created in Part 1
terraform init -reconfigure \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="prefix=state/cloud"

terraform plan -var-file=../variables.tfvars.json
terraform apply -var-file=../variables.tfvars.json -auto-approve
cd ..

echo -e "\n==============================================="
echo "  Terraform Infrastructure Provisioned!        "
echo "==============================================="
