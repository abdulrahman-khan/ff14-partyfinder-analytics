# upload csv to GCS 
# gsutil cp data/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv

# external table in BigQuery points directly to GCS, so no need to run jobs

# materializes it as a real native table in silver -> no more loading for every query


# resource "google_bigquery_table" "silver_worlds_clean" {
#   project             = var.project_id
#   dataset_id          = google_bigquery_dataset.silver.dataset_id
#   table_id            = "worlds_clean"
#   deletion_protection = false

#   schema = jsonencode([
#     { name = "world",      type = "STRING", mode = "REQUIRED" },
#     { name = "datacenter", type = "STRING", mode = "REQUIRED" },
#     { name = "region",     type = "STRING", mode = "REQUIRED" },
#   ])

#   labels = { project = "ff14-pf", env = "prod" }
# }