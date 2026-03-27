# NOTE: Build and push your image before running terraform apply:
#
#   gcloud auth configure-docker us-central1-docker.pkg.dev
#   docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest ./scraper
#   docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.scraper.repository_id}/scraper:latest"
}

resource "google_cloud_run_v2_job" "scraper" {
  name     = "ff14-pf-scraper"
  location = var.region

  template {
    template {
      service_account = google_service_account.scraper.email

      containers {
        image = local.image

        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.raw.name
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }

      max_retries = 2
      timeout     = "300s"
    }
  }

  labels = {
    project = "ff14-pf"
    env     = "prod"
  }

  depends_on = [
    google_artifact_registry_repository.scraper,
    google_storage_bucket.raw,
    google_service_account.scraper,
  ]
}

output "cloud_run_job_name" {
  value = google_cloud_run_v2_job.scraper.name
}