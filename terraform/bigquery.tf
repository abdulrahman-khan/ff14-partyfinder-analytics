# -- Datasets: Bronze / Silver / Gold -----------------------------------------
resource "google_bigquery_dataset" "bronze" {
  dataset_id  = "bronze"
  location    = var.region
  description = "Raw ingested data from GCS - append only"
  labels      = { project = "ff14-pf", env = "prod" }
}

resource "google_bigquery_dataset" "silver" {
  dataset_id  = "silver"
  location    = var.region
  description = "Cleaned and normalized listings - dims, facts, and deduped facts"
  labels      = { project = "ff14-pf", env = "prod" }
}

resource "google_bigquery_dataset" "gold" {
  dataset_id  = "gold"
  location    = var.region
  description = "Aggregated analytics-ready tables"
  labels      = { project = "ff14-pf", env = "prod" }
}

# -- Bronze: raw_listings ------------------------------------------------------
resource "google_bigquery_table" "bronze_raw_listings" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.bronze.dataset_id
  table_id            = "raw_listings"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "scraped_at"
  }

  schema = jsonencode([
    { name = "listing_id",     type = "STRING",    mode = "NULLABLE" },
    { name = "duty",           type = "STRING",    mode = "NULLABLE" },
    { name = "category",       type = "STRING",    mode = "NULLABLE" },
    { name = "description",    type = "STRING",    mode = "NULLABLE" },
    { name = "creator",        type = "STRING",    mode = "NULLABLE" },
    { name = "creator_server", type = "STRING",    mode = "NULLABLE" },
    { name = "world",          type = "STRING",    mode = "NULLABLE" },
    { name = "min_ilvl",       type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_filled",   type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_total",    type = "INTEGER",   mode = "NULLABLE" },
    { name = "slot_details",   type = "JSON",      mode = "NULLABLE" },
    { name = "expires_in",     type = "STRING",    mode = "NULLABLE" },
    { name = "updated_at",     type = "STRING",    mode = "NULLABLE" },
    { name = "scraped_at",     type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "source_file",    type = "STRING",    mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Bronze: raw_duties --------------------------------------------------------
resource "google_bigquery_table" "bronze_raw_duties" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.bronze.dataset_id
  table_id            = "raw_duties"
  deletion_protection = false

  schema = jsonencode([
    { name = "duty", type = "STRING", mode = "REQUIRED" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Bronze: file_loads --------------------------------------------------------
resource "google_bigquery_table" "file_loads" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.bronze.dataset_id
  table_id            = "file_loads"
  deletion_protection = false

  schema = jsonencode([
    { name = "file_name",    type = "STRING",    mode = "REQUIRED" },
    { name = "status",       type = "STRING",    mode = "REQUIRED" },
    { name = "started_at",   type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "completed_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "failed_at",    type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "error",        type = "STRING",    mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Bronze: failed_files ------------------------------------------------------
resource "google_bigquery_table" "failed_files" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.bronze.dataset_id
  table_id            = "failed_files"
  deletion_protection = false

  schema = jsonencode([
    { name = "file_name", type = "STRING",    mode = "REQUIRED" },
    { name = "failed_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "error",     type = "STRING",    mode = "REQUIRED" },
    { name = "context",   type = "STRING",    mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Silver: dim_duties --------------------------------------------------------
resource "google_bigquery_table" "silver_dim_duties" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.silver.dataset_id
  table_id            = "dim_duties"
  deletion_protection = false

  clustering = ["is_savage", "is_ultimate"]

  schema = jsonencode([
    { name = "duty_key",    type = "STRING",  mode = "NULLABLE" },
    { name = "duty",        type = "STRING",  mode = "NULLABLE" },
    { name = "is_savage",   type = "INTEGER", mode = "NULLABLE" },
    { name = "is_ultimate", type = "INTEGER", mode = "NULLABLE" },
    { name = "is_unreal",   type = "INTEGER", mode = "NULLABLE" },
    { name = "is_extreme",  type = "INTEGER", mode = "NULLABLE" },
    { name = "is_high_end", type = "INTEGER", mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Silver: dim_worlds --------------------------------------------------------
resource "google_bigquery_table" "silver_dim_worlds" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.silver.dataset_id
  table_id            = "dim_worlds"
  deletion_protection = false

  clustering = ["region", "datacenter"]

  schema = jsonencode([
    { name = "world_key",   type = "STRING", mode = "NULLABLE" },
    { name = "world",       type = "STRING", mode = "NULLABLE" },
    { name = "datacenter",  type = "STRING", mode = "NULLABLE" },
    { name = "region",      type = "STRING", mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Silver: fct_listings ------------------------------------------------------
resource "google_bigquery_table" "silver_fct_listings" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.silver.dataset_id
  table_id            = "fct_listings"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "scraped_date"
  }

  clustering = ["pf_world_key", "duty_key", "scraped_date"]

  schema = jsonencode([
    { name = "fct_key",              type = "STRING",    mode = "NULLABLE" },
    { name = "duty_key",             type = "STRING",    mode = "NULLABLE" },
    { name = "pf_world_key",         type = "STRING",    mode = "NULLABLE" },
    { name = "creator_world_key",    type = "STRING",    mode = "NULLABLE" },
    { name = "listing_id",           type = "STRING",    mode = "NULLABLE" },
    { name = "duty",                 type = "STRING",    mode = "NULLABLE" },
    { name = "pf_world",             type = "STRING",    mode = "NULLABLE" },
    { name = "creator_world",        type = "STRING",    mode = "NULLABLE" },
    { name = "source_file",          type = "STRING",    mode = "NULLABLE" },
    { name = "is_cross",             type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_loot",              type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_practice",          type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_clear",             type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_one_per_job",       type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_weekly_unclaimed",  type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_duty_completion",   type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_duty_complete",     type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_duty_incomplete",   type = "INTEGER",   mode = "NULLABLE" },
    { name = "description_clean",    type = "STRING",    mode = "NULLABLE" },
    { name = "pf_datacenter",        type = "STRING",    mode = "NULLABLE" },
    { name = "pf_region",            type = "STRING",    mode = "NULLABLE" },
    { name = "creator_datacenter",   type = "STRING",    mode = "NULLABLE" },
    { name = "creator_region",       type = "STRING",    mode = "NULLABLE" },
    { name = "is_traveller",         type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_voyager",           type = "INTEGER",   mode = "NULLABLE" },
    { name = "min_ilvl",             type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_filled",         type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_total",          type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_open",           type = "INTEGER",   mode = "NULLABLE" },
    { name = "open_tank_slots",      type = "INTEGER",   mode = "NULLABLE" },
    { name = "open_healer_slots",    type = "INTEGER",   mode = "NULLABLE" },
    { name = "open_dps_slots",       type = "INTEGER",   mode = "NULLABLE" },
    { name = "scraped_at",           type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "scraped_date",         type = "DATE",      mode = "NULLABLE" },
    { name = "scraped_time",         type = "TIME",      mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Silver: fct_listings_deduped ---------------------------------------------
resource "google_bigquery_table" "silver_fct_listings_deduped" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.silver.dataset_id
  table_id            = "fct_listings_deduped"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "scraped_date"
  }

  clustering = ["pf_world_key", "duty_key", "scraped_date"]

  schema = jsonencode([
    { name = "fct_key",              type = "STRING",    mode = "NULLABLE" },
    { name = "duty_key",             type = "STRING",    mode = "NULLABLE" },
    { name = "pf_world_key",         type = "STRING",    mode = "NULLABLE" },
    { name = "creator_world_key",    type = "STRING",    mode = "NULLABLE" },
    { name = "listing_id",           type = "STRING",    mode = "NULLABLE" },
    { name = "duty",                 type = "STRING",    mode = "NULLABLE" },
    { name = "pf_world",             type = "STRING",    mode = "NULLABLE" },
    { name = "creator_world",        type = "STRING",    mode = "NULLABLE" },
    { name = "source_file",          type = "STRING",    mode = "NULLABLE" },
    { name = "is_cross",             type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_loot",              type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_practice",          type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_clear",             type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_one_per_job",       type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_weekly_unclaimed",  type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_duty_completion",   type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_duty_complete",     type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_duty_incomplete",   type = "INTEGER",   mode = "NULLABLE" },
    { name = "description_clean",    type = "STRING",    mode = "NULLABLE" },
    { name = "pf_datacenter",        type = "STRING",    mode = "NULLABLE" },
    { name = "pf_region",            type = "STRING",    mode = "NULLABLE" },
    { name = "creator_datacenter",   type = "STRING",    mode = "NULLABLE" },
    { name = "creator_region",       type = "STRING",    mode = "NULLABLE" },
    { name = "is_traveller",         type = "INTEGER",   mode = "NULLABLE" },
    { name = "is_voyager",           type = "INTEGER",   mode = "NULLABLE" },
    { name = "min_ilvl",             type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_filled",         type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_total",          type = "INTEGER",   mode = "NULLABLE" },
    { name = "slots_open",           type = "INTEGER",   mode = "NULLABLE" },
    { name = "open_tank_slots",      type = "INTEGER",   mode = "NULLABLE" },
    { name = "open_healer_slots",    type = "INTEGER",   mode = "NULLABLE" },
    { name = "open_dps_slots",       type = "INTEGER",   mode = "NULLABLE" },
    { name = "scraped_at",           type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "scraped_date",         type = "DATE",      mode = "NULLABLE" },
    { name = "scraped_time",         type = "TIME",      mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Gold: duty_stats ----------------------------------------------------------
resource "google_bigquery_table" "gold_duty_stats" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.gold.dataset_id
  table_id            = "duty_stats"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "date"
  }

  schema = jsonencode([
    { name = "duty",                    type = "STRING",  mode = "NULLABLE" },
    { name = "is_cross",                type = "INTEGER", mode = "NULLABLE" },
    { name = "pf_world",                type = "STRING",  mode = "NULLABLE" },
    { name = "pf_datacenter",           type = "STRING",  mode = "NULLABLE" },
    { name = "pf_region",               type = "STRING",  mode = "NULLABLE" },
    { name = "date",                    type = "DATE",    mode = "NULLABLE" },
    { name = "hour",                    type = "INTEGER", mode = "NULLABLE" },
    { name = "listing_count",           type = "INTEGER", mode = "NULLABLE" },
    { name = "avg_party_size",          type = "FLOAT",   mode = "NULLABLE" },
    { name = "avg_min_ilvl",            type = "FLOAT",   mode = "NULLABLE" },
    { name = "listings_needing_tank",   type = "INTEGER", mode = "NULLABLE" },
    { name = "listings_needing_healer", type = "INTEGER", mode = "NULLABLE" },
    { name = "listings_needing_dps",    type = "INTEGER", mode = "NULLABLE" },
    { name = "avg_fill_rate_pct",       type = "FLOAT",   mode = "NULLABLE" }
  ])

  labels = { project = "ff14-pf", env = "prod" }
}

# -- Dataset IAM ---------------------------------------------------------------
resource "google_bigquery_dataset_iam_member" "pipeline_bronze" {
  dataset_id = google_bigquery_dataset.bronze.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_silver" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_gold" {
  dataset_id = google_bigquery_dataset.gold.dataset_id
  role       "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}