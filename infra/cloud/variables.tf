variable "project_id" {
  type        = string
  description = "The unique ID of the GCP project (must match Part 1)"
}

variable "region" {
  type        = string
  description = "The default region for GCS and Cloud Run"
  default     = "us-central1"
}

variable "db_region" {
  type        = string
  description = "The default region for Firestore"
  default     = "europe-west1"
}

variable "admin_group_email" {
  type        = string
  description = "The Google Group email for administrator IAM bindings (editor role — groups cannot be owners)"
  default     = ""
}

variable "owner_email" {
  type        = string
  description = "Individual user email that holds roles/owner. Required: GCP mandates at least one user owner (groups/SAs cannot hold owner)"
  default     = ""
}

variable "billing_account" {
  type        = string
  description = "The billing account ID to associate with the project"
}

variable "state_bucket_name" {
  type        = string
  description = "The name of the GCS bucket for Terraform state"
}
