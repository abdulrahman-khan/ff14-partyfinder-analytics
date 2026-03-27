
# -- Worlds Data (csv file location
resource "google_storage_bucket_object" "worlds_csv" {
  name   = "worlds_data/worlds.csv"
  bucket = google_storage_bucket.raw.name
  source = "${path.module}/../data/worlds.csv"
}

# -- BigQuery external table ---------------------------------------------------
resource "google_bigquery_table" "bronze_worlds" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.bronze.dataset_id
  table_id   = "worlds"

  description         = "FFXIV world → datacenter → region reference. Source: GCS CSV."
  deletion_protection = false

  external_data_configuration {
    source_uris   = ["gs://${google_storage_bucket.raw.name}/worlds_data/worlds.csv"]
    source_format = "CSV"
    autodetect    = false

    csv_options {
      quote             = "\""
      field_delimiter   = ","
      skip_leading_rows = 1
    }

    schema = jsonencode([
      { name = "world",      type = "STRING", mode = "REQUIRED" },
      { name = "datacenter", type = "STRING", mode = "REQUIRED" },
      { name = "region",     type = "STRING", mode = "REQUIRED" },
    ])
  }

  depends_on = [google_storage_bucket_object.worlds_csv]
}
