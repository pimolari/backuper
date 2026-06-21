variable "project_name" {
  type        = string
  description = "The display name of the GCP project"
}

variable "project_id" {
  type        = string
  description = "The unique ID of the GCP project"
}

variable "org_id" {
  type        = string
  description = "The numeric Organization ID (optional)"
  default     = ""
}

variable "billing_account" {
  type        = string
  description = "The billing account ID to associate with the project"
}

variable "region" {
  type        = string
  description = "The default region for GCS and Cloud Run"
  default     = "us-central1"
}

variable "admin_group_email" {
  type        = string
  description = "The Google Group email for administrator IAM bindings"
}

variable "state_bucket_name" {
  type        = string
  description = "The name of the GCS bucket for Terraform state"
}
