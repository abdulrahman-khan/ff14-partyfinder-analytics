# scraping trigger (15mins)
resource "google_cloud_scheduler_job" "scraper_trigger" {
  name             = "ff14-pf-scraper-trigger"
  description      = "Trigger the FF14 PF scraper Cloud Run job every 15 minutes"
  schedule         = "*/15 * * * *"
  time_zone        = "UTC"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.scraper.name}:run"

    oauth_token {
      service_account_email = google_service_account.scraper.email
    }
  }

  depends_on = [google_cloud_run_v2_job.scraper]
}

# NOTE: loading is manual only (cost control). The GCS -> Bronze loader is run on
# demand from the gcloud UI or `make run-loader`; it then triggers the Dataform
# pipeline itself (see services/loader/gcs_to_bronze.py). No hourly loader schedule.