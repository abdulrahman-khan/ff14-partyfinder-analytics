# FFXIV Party Finder Data Warehouse

Scrapes live pf listings from [xivpf.com](https://xivpf.com), ingesting into GCP BigQuery Data Warehouse. 

---

<!-- ## Architecture
Add architecture flow diagram here
-->


## Pipeline overview

```
xivpf.com
    ↓ every 15 min — Cloud Run (scraper)
GCS: raw/YYYY/MM/DD/HHMMSS.json
    ↓ every hour at :05 — Cloud Workflows
    ├── Cloud Run (duty-extractor) → bronze.duties
    ├── wait 30s
    ├── Cloud Run (loader) → bronze.raw_listings
    ├── wait 120s
    └── Dataform
            ├── silver.dim_duties                      (table)
            ├── silver.dim_worlds                      (stub — manually managed)
            ├── silver.fct_listings                    (incremental)
            ├── silver.fct_listings_deduped            (view)
            ├── gold.spine_hour_datacenter             (table)
            ├── gold.mart_activity_hour_datacenter     (incremental)
            ├── gold.mart_this_week_na_by_datacenter   (table)
            ├── gold.mart_last_week_na_by_datacenter   (table)
            ├── gold.mart_this_week_na_traveller_movement (table)
            └── gold.mart_last_week_na_traveller_movement (table)
```


### Schema

```
silver.dim_worlds    silver.dim_duties
        ↑                    ↑
        └── silver.fct_listings ──┐
                                  ↓
                    gold.spine_hour_datacenter
                            ↓
              gold.mart_activity_hour_datacenter
              gold.mart_*_by_datacenter
              gold.mart_*_traveller_movement
```





## Getting started

### 1. Authenticate
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
```

### 2. Enable GCP APIs
```bash
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com bigquery.googleapis.com artifactregistry.googleapis.com workflows.googleapis.com dataform.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
```

### 3. Configure Terraform
Edit `terraform/terraform.tfvars`:
```hcl
project_id         = "your-project-id"
region             = "us-central1"
dataform_git_url   = "https://github.com/yourname/ff14-pf.git"
dataform_git_token = "ghp_xxxxxxxxxxxx"
```

### 4. Deploy infrastructure
```bash
cd terraform
terraform apply -target=google_storage_bucket.raw -target=google_artifact_registry_repository.scraper
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest ./scraper
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest ./pipeline
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/duty-extractor:latest ./duty_extractor
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/duty-extractor:latest
terraform apply
```

### 5. Set up Dataform credentials
```bash
cd ../dataform
dataform init-creds   # select BigQuery, then ADC
```

### 6. Load worlds reference table (one-time)
```bash
bq query --nouse_legacy_sql --project_id=ff14-pf-data "$(Get-Content scripts/load_dim_worlds.sql -Raw)"
```



### Manually Run Pipelines / Dataforms

```bash
gcloud run jobs execute ff14-pf-scraper --region=us-central1

gcloud run jobs execute ff14-pf-duty-extractor --region=us-central1

gcloud run jobs execute ff14-pf-loader --region=us-central1

dataform run
```

---

## Updating and redeploying

Rebuild and push the relevant image after any Python changes:

```bash
# scraper
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest ./scraper
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest
gcloud run jobs execute ff14-pf-scraper --region=us-central1

# loader
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest ./pipeline
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest
gcloud run jobs execute ff14-pf-loader --region=us-central1

# duty extractor
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/duty-extractor:latest ./duty_extractor
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/duty-extractor:latest
gcloud run jobs execute ff14-pf-duty-extractor --region=us-central1
```

For Dataform changes, push to `main` — the Dataform repo in GCP pulls from Git automatically on each pipeline run.

---


## Disclaimer

This project scrapes publicly visible data from [xivpf.com](https://xivpf.com). 
Not affiliated with Square Enix.