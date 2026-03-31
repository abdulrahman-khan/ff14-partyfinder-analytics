# FFXIV Party Finder Data Warehouse

Production-grade data engineering pipeline on GCP that continuously scrapes live party finder listings from [xivpf.com](https://xivpf.com), ingesting them into a medallion data warehouse on BigQuery, and surfaces aggregated analytics through Looker Studio.

---

<!-- ## Architecture
Add architecture flow diagram here 

---

-->



## What it demonstrates
- **Medallion architecture** - Raw data is never mutated. Bronze is append-only, Silver cleans and enriches data, Gold aggregates for analytics.
- **Idempotent Pipelines** - Pipeline tracks file state in a `file_loads` table using an append-only log
- **Automated Scraping and ETL Jobs** - Web scraping script and loading ETL pipeline run as containerised Cloud Run Jobs on Cloud Scheduler triggers, scaling to zero between runs.
- **Fault-tolerant error handling** - Scraper errors write to a dead-letter/ prefix in GCS and loader failures are recorded to `bronze.failed_files` in BigQuery, keeping the pipeline running while preserving full error context for debugging.
---

## Medallion layers

| Layer | Dataset | Description |
|---|---|---|
| Bronze | `bronze` | Raw JSON flattened from GCS, append-only |
| Silver | `silver` | Cleaned, typed, deduplicated, enriched with datacenter and region data |
| Gold | `gold` | Hourly aggregates for analytics - duty popularity, role demand, fill rates |

## Repo structure
```
ff14-pf/
├── terraform/
│   ├── main.tf               # Provider and project config
│   ├── variables.tf
│   ├── storage.tf            # Google Cloud Storage bucket
│   ├── artifact.tf           # Artifact Registry (Docker)
│   ├── iam.tf                # Service accounts + least-privilege roles
│   ├── bigquery.tf           # All datasets and tables
│   ├── bigquery_worlds.tf    # External worlds reference table
│   ├── cloud_run.tf          # Scraper + loader Cloud Run Jobs
│   ├── scheduler.tf          # Cloud Scheduler triggers
│   ├── workflows.tf          # Cloud Workflows pipeline orchestration
│   └── dataform.tf           # Dataform repository + Git connection
├── scraper/
│   ├── main.py               # xivpf.com web scraper script
│   └── Dockerfile
├── pipeline/
│   ├── gcs_to_bronze.py      # data pipeline GCS → BigQuery
│   └── Dockerfile
├── dataform/
│   ├── workflow_settings.yaml
│   └── definitions/
│       ├── bronze/           
│       ├── silver/           
│       └── gold/            
└── data/
    └── worlds.csv            # World/Datacenter/Region backfill data (not in github repo)
```

---

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- [Terraform](https://developer.hashicorp.com/terraform/install)
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [Dataform CLI](https://docs.dataform.co/dataform-cli) - `npm i -g @dataform/cli`
- A GCP project with billing enabled
- A GitHub repo and personal access token (for Dataform Git connection)

---

<!--

## Getting started

### 1. Authenticate GCloud CLI
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

# Create bucket and registry first
terraform apply -target=google_storage_bucket.raw -target=google_artifact_registry_repository.scraper

# Configure Docker auth
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push scraper image
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest ./scraper
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest

# Build and push loader image
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest ./pipeline
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest

# Deploy everything else
terraform apply
```

### 5. Set up Dataform credentials
```bash
cd ../dataform
dataform init-creds   # select BigQuery, then ADC
```



---

-->


## Running the pipeline manually

Use this sequence to trigger and verify the full pipeline end to end:
```bash
# 1. Trigger the loader (picks up any new files from GCS)
gcloud run jobs execute ff14-pf-loader --region=us-central1

# 2. Check execution logs and confirm rows land in bronze layer
gcloud run jobs executions list --job=ff14-pf-loader --region=us-central1

bq query --nouse_legacy_sql "SELECT COUNT(*) FROM bronze.raw_listings"

# 3. Run Dataform transforms
dataform run

```

---

## Updating and redeploying

For future changes to scraper/loader, rebuild and push image. Then reexecute jobs.  
```bash
# Rebuild and push loader after changes to gcs_to_bronze.py
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest ./pipeline
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest
gcloud run jobs execute ff14-pf-loader --region=us-central1

# Rebuild and push scraper after changes to main.py
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest ./scraper
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest
gcloud run jobs execute ff14-pf-scraper --region=us-central1
```

For Dataform changes push to `main` - Dataform repo in GCP pulls from Git automatically

---

## Dataform transforms
```bash
dataform compile              # validate SQL and ref() resolution - no BQ connection needed
dataform run                  # run incremental pipeline
dataform run --full-refresh   # rebuild all tables from scratch (use after schema changes)
```


---

## Disclaimer

This project scrapes public data from [xivpf.com](https://xivpf.com). Not affiliated with Square Enix.
