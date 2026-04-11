

remove these comments before running this script
makes silver.dim_worlds from the worlds.csv
run manually if the worlds CSV changes

bronze.raw_worlds external table must exist and point at
gs://ff14-pf-data-raw/worlds_data/worlds.csv
upload worlds.csv to GCS
gsutil cp data/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv
run script
bq query --nouse_legacy_sql --project_id=ff14-pf-data --flagfile=scripts/load_dim_worlds.sql