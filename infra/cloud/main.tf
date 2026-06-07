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

# IAM bindings for a Google Group with administrator permissions (Owner role)
resource "google_project_iam_binding" "admin_group_binding" {
  project = var.project_id
  role    = "roles/owner"

  members = [
    "user:gerardo.mongelli@gmail.com"
  ]
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

# Grant Datastore Owner permission to the Service Account
resource "google_project_iam_member" "datastore_user" {
  project = var.project_id
  role    = "roles/datastore.owner"
  member  = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}


# Grant Storage Admin permission to the Service Account (to create/delete user GCS buckets dynamically)
resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.cloud_run_backend_sa.email}"
}
