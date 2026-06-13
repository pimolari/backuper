#!/usr/bin/env bash

# common.sh
# Shared environment configuration and helper functions for deployment scripts.

# Fail on error
set -e

# Change directory to the infra folder (where the script is sourced from)
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "Parsing variables from variables.tfvars.json..."
if [ ! -f "variables.tfvars.json" ]; then
    echo "Error: variables.tfvars.json not found in $(pwd)!"
    exit 1
fi

# Parse configuration using Python to avoid external dependencies like jq
export PROJECT_ID=$(python3 -c "import json; print(json.load(open('variables.tfvars.json'))['project_id'])")
export REGION=$(python3 -c "import json; print(json.load(open('variables.tfvars.json')).get('region', 'europe-west1'))")
export FRONTEND_SERVICE_ACCOUNT_EMAIL="backuper-frontend-client@${PROJECT_ID}.iam.gserviceaccount.com"
export BACKEND_SERVICE_ACCOUNT_EMAIL="backuper-backend-client@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Frontend Service Account: $FRONTEND_SERVICE_ACCOUNT_EMAIL"
echo "Backend Service Account: $BACKEND_SERVICE_ACCOUNT_EMAIL"

# Setup the active project configuration for gcloud
echo "Configuring gcloud project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID"
