output "project_id" {
  value       = google_project.project.project_id
  description = "The project ID of the created project"
}

output "state_bucket_name" {
  value       = google_storage_bucket.state_bucket.name
  description = "The GCS bucket name for Terraform State"
}
