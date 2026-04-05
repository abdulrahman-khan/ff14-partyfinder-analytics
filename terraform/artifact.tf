resource "google_artifact_registry_repository" "scraper" {
  repository_id = "ff14-pf-scraper"
  location      = var.region
  format        = "DOCKER"
  description   = "Docker images for the FF14 Party Finder scraper"

  labels = {
    project = "ff14-pf"
    env     = "prod"
  }
}

output "docker_repo" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.scraper.repository_id}"
  description = "Full Artifact Registry path - use this as your Docker image prefix"
}