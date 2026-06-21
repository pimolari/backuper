#!/usr/bin/env bash

# Fail on error
set -e

# Change directory to the infra folder (where the script is located)
cd "$(dirname "$0")"

echo "==============================================="
echo "  Deploying Backuper Services to Cloud Run    "
echo "==============================================="

# 1. Load shared configuration
source ./common.sh

# 2. Create Artifact Registry repository for Docker images if it doesn't exist
echo "Checking if Artifact Registry repository 'backuper-repo' exists..."
if ! gcloud artifacts repositories describe backuper-repo --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo "Creating Artifact Registry repository..."
    gcloud artifacts repositories create backuper-repo \
      --repository-format=docker \
      --location="$REGION" \
      --project="$PROJECT_ID" \
      --description="Backuper container images repository"
else
    echo "Artifact Registry repository 'backuper-repo' already exists."
fi

# 3. Build container images using Google Cloud Build
echo "Building backend container image with Cloud Build..."
gcloud builds submit --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/backuper-repo/backend:latest" ../backend --project="${PROJECT_ID}"

echo "Building frontend container image with Cloud Build..."
gcloud builds submit --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/backuper-repo/frontend:latest" ../frontend --project="${PROJECT_ID}"

# 4. Deploy Backend service to Google Cloud Run
echo "Deploying backend to Cloud Run..."
gcloud run deploy backend \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/backuper-repo/backend:latest" \
  --platform=managed \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars="USE_REAL_GCP=true" \
  --service-account="$BACKEND_SERVICE_ACCOUNT_EMAIL" \
  --timeout=1800 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5

# Get backend URL for proxying
echo "Retrieving backend URL..."
BACKEND_URL=$(gcloud run services describe backend --platform=managed --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)")
echo "Backend URL: $BACKEND_URL"

# 4.5. Update Pub/Sub Push Subscriptions
echo "Configuring Pub/Sub Push endpoints for asynchronous processing..."
gcloud pubsub subscriptions update generate-snapshot-sub \
  --push-endpoint="${BACKEND_URL}/api/files/internal/snapshot" \
  --project="$PROJECT_ID"

gcloud pubsub subscriptions update bulk-delete-sub \
  --push-endpoint="${BACKEND_URL}/api/files/internal/bulk-delete" \
  --project="$PROJECT_ID"

# 5. Deploy Frontend service to Google Cloud Run (injecting BACKEND_URL)
echo "Deploying frontend to Cloud Run..."
gcloud run deploy frontend \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/backuper-repo/frontend:latest" \
  --platform=managed \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars="BACKEND_URL=${BACKEND_URL}" \
  --service-account="$FRONTEND_SERVICE_ACCOUNT_EMAIL" \
  --timeout=1800 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5

FRONTEND_URL=$(gcloud run services describe frontend --platform=managed --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)")

echo -e "\n==============================================="
echo "  Deploy complete!                             "
echo "  Frontend URL: $FRONTEND_URL"
echo "  Backend URL:  $BACKEND_URL"
echo "==============================================="
