output "cloud_run_frontend_sa_email" {
  value       = google_service_account.cloud_run_frontend_sa.email
  description = "The email address of the created Cloud Run Frontend Service Account"
}

output "cloud_run_backend_sa_email" {
  value       = google_service_account.cloud_run_backend_sa.email
  description = "The email address of the created Cloud Run Backend Service Account"
}
