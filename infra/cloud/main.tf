terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# IAM binding for the admin group/user (conditionally applied when admin_group_email is set)
resource "google_project_iam_member" "admin_group_binding" {
  count   = var.admin_group_email != "" ? 1 : 0
  project = var.project_id
  role    = "roles/owner"
  member  = "group:${var.admin_group_email}"
}

# Provision Firestore/Datastore Database in Datastore Mode
resource "google_firestore_database" "datastore_db" {
  project     = var.project_id
  name        = "backuper-db"
  location_id = var.region
  type        = "DATASTORE_MODE"

  # Prevent deletion of the database
  lifecycle {
    prevent_destroy = true
  }
}

# Create Service Account for Cloud Run Services
resource "google_service_account" "cloud_run_frontend_sa" {
  account_id   = "backuper-frontend-client"
  display_name = "Backuper Cloud Frontend Service Run Service Account"
  project      = var.project_id
}

resource "google_service_account" "cloud_run_backend_sa" {
  account_id   = "backuper-backend-client"
  display_name = "Backuper Cloud Backend Service Run Service Account"
  project      = var.project_id
}

# Grant Datastore User permission to the Service Account (least privilege)
resource "google_project_iam_member" "datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}


# Grant Storage Object Admin (scoped to backuper-* buckets via condition) — avoids project-wide admin
resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"

  condition {
    title       = "backuper_buckets_only"
    description = "Restrict storage access to backuper-prefixed buckets"
    expression  = "resource.name.startsWith(\"projects/_/buckets/backuper-\")"
  }
}

# ---------------------------------------------------------
# Pub/Sub Infrastructure for Asynchronous Snapshot Generation
# ---------------------------------------------------------

resource "google_pubsub_topic" "generate_snapshot" {
  name    = "generate-snapshot"
  project = var.project_id
}

resource "google_pubsub_subscription" "generate_snapshot_sub" {
  name    = "generate-snapshot-sub"
  topic   = google_pubsub_topic.generate_snapshot.name
  project = var.project_id

  ack_deadline_seconds = 20

  # Retain unacknowledged messages for 7 days
  message_retention_duration = "604800s"
}

# Grant Pub/Sub Publisher role to backend SA (to trigger snapshots)
resource "google_pubsub_topic_iam_member" "backend_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.generate_snapshot.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}

# Grant Pub/Sub Subscriber role to backend SA (for the worker)
resource "google_pubsub_subscription_iam_member" "backend_subscriber" {
  project      = var.project_id
  subscription = google_pubsub_subscription.generate_snapshot_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}

# ---------------------------------------------------------
# Pub/Sub Infrastructure for Asynchronous Bulk Deletion
# ---------------------------------------------------------

resource "google_pubsub_topic" "bulk_delete" {
  name    = "bulk-delete"
  project = var.project_id
}

resource "google_pubsub_subscription" "bulk_delete_sub" {
  name    = "bulk-delete-sub"
  topic   = google_pubsub_topic.bulk_delete.name
  project = var.project_id

  ack_deadline_seconds = 600

  # Retain unacknowledged messages for 7 days
  message_retention_duration = "604800s"
}

# Grant Pub/Sub Publisher role to backend SA (to trigger bulk deletes)
resource "google_pubsub_topic_iam_member" "backend_bulk_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.bulk_delete.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}

# Grant Pub/Sub Subscriber role to backend SA (for receiving bulk deletes)
resource "google_pubsub_subscription_iam_member" "backend_bulk_subscriber" {
  project      = var.project_id
  subscription = google_pubsub_subscription.bulk_delete_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}

