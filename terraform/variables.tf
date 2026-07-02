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

variable "billing_account" {
  description = "Cloud Billing account ID (format XXXXXX-XXXXXX-XXXXXX). Find via: gcloud billing accounts list"
  type        = string
}

variable "alert_email" {
  description = "Email address for budget and pipeline failure alerts"
  type        = string
  default     = "ak47thefirelord@gmail.com"
}

variable "analyst_group" {
  description = "Google group granted read (dataViewer) access to silver + gold ONLY"
  type        = string
  default     = "abdulkhanyyz@gmail.com"
}

variable "bronze_reader_group" {
  description = "Google group of trusted devs granted read (dataViewer) access to the bronze dataset."
  type        = string
  default     = "abdulkhanyyz@gmail.com"
}