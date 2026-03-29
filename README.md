


docker comands to run pipeline 



docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest ./pipeline

docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest

gcloud run jobs execute ff14-pf-loader --region=us-central1






---


# 1. manually trigger the loader
gcloud run jobs execute ff14-pf-loader --region=us-central1

# 2. check logs
gcloud run jobs executions list --job=ff14-pf-loader --region=us-central1

# 3. confirm rows landed in bronze
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM bronze.raw_listings"

# 4. manually run dataform
dataform run

# 5. confirm silver and gold populated
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM silver.listings_clean"
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM gold.duty_stats"
