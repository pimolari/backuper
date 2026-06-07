#!/usr/bin/env bash

# Fail on error
set -e

# Change directory to the infra folder (where the script is located)
cd "$(dirname "$0")"

echo "==============================================="
echo "  Deploying GCP Infrastructure via Terraform   "
echo "==============================================="

# 1. Parse variables from JSON file using Python to avoid external dependencies like jq
echo "Parsing variables from variables.tfvars.json..."
if [ ! -f "variables.tfvars.json" ]; then
    echo "Error: variables.tfvars.json not found!"
    exit 1
fi

PROJECT_ID=$(python3 -c "import json; print(json.load(open('variables.tfvars.json'))['project_id'])")
STATE_BUCKET=$(python3 -c "import json; print(json.load(open('variables.tfvars.json'))['state_bucket_name'])")
REGION=$(python3 -c "import json; print(json.load(open('variables.tfvars.json')).get('region', 'europe-west1'))")
ADMIN_GROUP_EMAIL=$(python3 -c "import json; print(json.load(open('variables.tfvars.json')).get('admin_group_email', ''))")

echo "Project ID: $PROJECT_ID"
echo "State Bucket: $STATE_BUCKET"
echo "Region: $REGION"
echo "Admin Group Email: $ADMIN_GROUP_EMAIL"

# 2. Execute Part 1 (Bootstrap project & storage bucket for remote state)
echo -e "\n--- Step 1: Deploying Project Bootstrap (Part 1) ---"
cd local
terraform init
terraform plan -var-file=../variables.tfvars.json
terraform apply -var-file=../variables.tfvars.json -auto-approve
cd ..


echo -e "\n==============================================="
echo "  Terraform Infrastructure Provisioned!        "
echo "==============================================="
