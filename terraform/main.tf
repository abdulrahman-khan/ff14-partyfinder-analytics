terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # billingbudgets.googleapis.com (and other user-project-scoped APIs) require a
  # quota/billing project header. The provider only sends it when user_project_override
  # is on; otherwise the call bills the credential's owning project and 403s SERVICE_DISABLED.
  billing_project       = var.project_id
  user_project_override = true
}

provider "google-beta" {
  project = var.project_id
  region  = var.region

  billing_project       = var.project_id
  user_project_override = true
}