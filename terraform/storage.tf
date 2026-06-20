# -- GCS Bucket: Raw scraper output + dead-letter -----------------------------
resource "google_storage_bucket" "raw" {
  name          = "${var.project_id}-raw"
  location      = var.region
  force_destroy = false

  # No lifecycle deletion rules: raw/ is the immutable source of truth for all
  # scraped data and must never be auto-deleted (see CLAUDE.md hard rule).

  uniform_bucket_level_access = true

  labels = {
    project = "ff14-pf"
    env     = "prod"
  }
}

output "raw_bucket_name" {
  value = google_storage_bucket.raw.name
}