



resource "google_dataform_repository" "ff14" {
  provider = google-beta
  name     = "ff14-pf-dataform"
  region   = var.region
  project  = var.project_id

  git_remote_settings {
    url                                 = var.dataform_git_url
    default_branch                      = "main"
    authentication_token_secret_version = google_secret_manager_secret_version.dataform_git_token.id
  }

  workspace_compilation_overrides {
    default_database = var.project_id
  }
}

resource "google_secret_manager_secret" "dataform_git_token" {
  secret_id = "dataform-git-token"
  project   = var.project_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "dataform_git_token" {
  secret      = google_secret_manager_secret.dataform_git_token.id
  secret_data = var.dataform_git_token
}

resource "google_secret_manager_secret_iam_member" "dataform_secret_access" {
  secret_id = google_secret_manager_secret.dataform_git_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-dataform.iam.gserviceaccount.com"
}

data "google_project" "project" {
  project_id = var.project_id
}