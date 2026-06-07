terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Provider used for project bootstrapping
provider "google" {
  region = var.region
}

# Create the GCP project
resource "google_project" "project" {
  name            = var.project_name
  project_id      = var.project_id
  org_id          = var.org_id != "" ? var.org_id : null
  billing_account = var.billing_account
}

# Enable GCP Services
resource "google_project_service" "services" {
  for_each = toset([
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "datastore.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com"
  ])
  project            = google_project.project.project_id
  service            = each.key
  disable_on_destroy = false
}

# Grant Datastore Owner permission to the Service Account
resource "google_project_iam_member" "admin_group" {
  project = var.project_id
  role    = "roles/editor"
  member  = "group:${var.admin_group_email}"

  depends_on = [
    google_project_service.services
  ]
}

# Create GCS Bucket to hold the Terraform State for Part 2 and future resources
resource "google_storage_bucket" "state_bucket" {
  name          = var.state_bucket_name
  project       = google_project.project.project_id
  location      = var.region
  storage_class = "STANDARD"

  versioning {
    enabled = true
  }

  # Prevent accidental destruction of state bucket
  lifecycle {
    prevent_destroy = false
  }

  depends_on = [
    google_project_service.services["storage.googleapis.com"]
  ]
}
