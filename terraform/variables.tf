variable "project_id" {
  description = "Your GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "dataform_git_url" {
  description = "HTTPS URL of your GitHub repo, e.g. https://github.com/yourname/ff14-pf.git"
  type        = string
}

variable "dataform_git_token" {
  description = "GitHub personal access token with repo read access"
  type        = string
  sensitive   = true
}