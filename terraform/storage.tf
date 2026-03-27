# -- GCS Bucket: Raw scraper output + dead-letter -----------------------------
resource "google_storage_bucket" "raw" {
  name          = "${var.project_id}-raw"
  location      = var.region
  force_destroy = false

  lifecycle_rule {
    condition {
      age            = 90
      matches_prefix = ["raw/"]
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age            = 180
      matches_prefix = ["dead-letter/"]
    }
    action {
      type = "Delete"
    }
  }

  uniform_bucket_level_access = true

  labels = {
    project = "ff14-pf"
    env     = "prod"
  }
}

output "raw_bucket_name" {
  value = google_storage_bucket.raw.name
}