-- One-time script to materialize worlds_clean into the silver layer.
-- Run manually in the when the worlds CSV changes.
-- 
-- Prerequisites: bronze.worlds external table must exist and point at
-- gs://ff14-pf-data-raw/worlds_data/worlds.csv

-- tell terraform this script exists 
-- terraform import google_bigquery_table.silver_worlds_clean ff14-pf-data/silver/worlds_clean

-- 

-- upload worlds.csv
-- gsutil cp data/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv
-- terminal command to run query
-- bq query --nouse_legacy_sql --project_id=ff14-pf-data --flagfile=scripts/load_worlds_clean.sql


CREATE OR REPLACE TABLE `ff14-pf-data.silver.worlds_clean` AS
SELECT
  TRIM(world,      "'") AS world,
  TRIM(datacenter, "'") AS datacenter,
  TRIM(region,     "'") AS region
FROM `ff14-pf-data.bronze.worlds`