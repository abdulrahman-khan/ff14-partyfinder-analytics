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

# pipelines
resource "google_project_iam_member" "pipeline_workflows_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# The workflow executes the duty-extractor and dataform-runner Cloud Run jobs via
# the jobs :run API, which requires run.jobs.run (granted by roles/run.invoker).
# Without this the workflow 403s on its first step.
resource "google_project_iam_member" "pipeline_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# The workflow uses the Cloud Run connector to BLOCK until each job completes,
# which polls execution/operation status - run.invoker runs the job, run.viewer
# reads its status.
resource "google_project_iam_member" "pipeline_run_viewer" {
  project = var.project_id
  role    = "roles/run.viewer"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_dataform_editor" {
  project = var.project_id
  role    = "roles/dataform.editor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}
