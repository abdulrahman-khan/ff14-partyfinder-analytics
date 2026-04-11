-- One-time script to materialize worlds_clean into the silver layer.
-- Run manually when the worlds CSV changes.
-- 
-- Prerequisites: bronze.raw_worlds external table must exist and point at
-- gs://ff14-pf-data-raw/worlds_data/worlds.csv

-- upload worlds.csv
-- gsutil cp data/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv
-- terminal command to run query
-- bq query --nouse_legacy_sql --project_id=ff14-pf-data --flagfile=scripts/load_worlds_clean.sql

CREATE OR REPLACE TABLE `ff14-pf-data.silver.worlds_clean` AS
SELECT
  TRIM(world,      "'") AS world,
  TRIM(datacenter, "'") AS datacenter,
  TRIM(region,     "'") AS region
FROM `ff14-pf-data.bronze.raw_worlds`