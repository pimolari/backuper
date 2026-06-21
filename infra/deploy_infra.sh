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
REGION=$(python3 -c "import json; print(json.load(open('variables.tfvars.json')).get('region', 'us-central1'))")
ADMIN_GROUP_EMAIL=$(python3 -c "import json, os; print(json.load(open('variables.private.tfvars.json')).get('admin_group_email', '')) if os.path.exists('variables.private.tfvars.json') else print('')")

echo "Project ID: $PROJECT_ID"
echo "State Bucket: $STATE_BUCKET"
echo "Region: $REGION"
echo "Admin Group Email: $ADMIN_GROUP_EMAIL"

# 2. Execute Part 1 (Bootstrap project & storage bucket for remote state)
echo -e "\n--- Step 1: Deploying Project Bootstrap (Part 1) ---"
cd part1
terraform init
terraform plan -var-file=../variables.tfvars.json -var-file=../variables.private.tfvars.json
#terraform apply -var-file=../variables.tfvars.json -var-file=../variables.private.tfvars.json -auto-approve
cd ..

# 3. Execute Part 2 (Remote state storage, Datastore, and Service Account permissions)
echo -e "\n--- Step 2: Deploying Main Resources (Part 2) ---"
cd part2
# Initialize with GCS remote state configuration pointing to the bucket created in Part 1
terraform init -reconfigure \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="prefix=state/part2"

terraform plan -var-file=../variables.tfvars.json -var-file=../variables.private.tfvars.json
#terraform apply -var-file=../variables.tfvars.json -var-file=../variables.private.tfvars.json -auto-approve
cd ..

echo -e "\n==============================================="
echo "  Terraform Infrastructure Provisioned!        "
echo "==============================================="
