resource "google_service_account" "scraper" {
  account_id   = "ff14-pf-scraper"
  display_name = "FF14 PF Scraper"
  description  = "Identity for the Cloud Run scraper job"
}

resource "google_storage_bucket_iam_member" "scraper_writer" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.scraper.email}"
}

resource "google_project_iam_member" "scraper_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.scraper.email}"
}

resource "google_service_account" "pipeline" {
  account_id   = "ff14-pf-pipeline"
  display_name = "FF14 PF Pipeline"
  description  = "Identity for Cloud Workflows and Dataform pipeline"
}

resource "google_storage_bucket_iam_member" "pipeline_reader" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "scheduler_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.scraper.email}"
}

output "scraper_sa_email" {
  value = google_service_account.scraper.email
}

output "pipeline_sa_email" {
  value = google_service_account.pipeline.email
}