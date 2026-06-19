# FFXIV Party Finder Data Warehouse

End-to-end GCP data pipeline that scrapes live Party Finder listings from
[xivpf.com](https://xivpf.com) every 15 minutes, lands them in BigQuery via a medallion
architecture (bronze → silver → gold), and runs hourly SQL transforms with Dataform. All
infrastructure is managed with Terraform.

**GCP project:** `ff14-pf-data` · **Region:** `us-central1`

## Documentation

- [docs/architecture.md](docs/architecture.md) — repo layout, data flow, medallion schema, design decisions
- [docs/gold_marts.md](docs/gold_marts.md) — gold marts catalog + the lifecycle model
- [docs/observability.md](docs/observability.md) — logging & failure-alerting runbook
- [docs/improvements.md](docs/improvements.md) — backlog / improvement opportunities

## Pipeline overview

```
xivpf.com
    ↓ every 15 min — Cloud Run (scraper)
GCS: raw/YYYY/MM/DD/HHMMSS.json
    ↓ every hour at :05 — Cloud Workflows
    ├── Cloud Run (duty-extractor) → bronze.duties
    ├── wait 30s
    ├── Cloud Run (loader) → bronze.raw_listings
    ├── wait 150s
    └── Dataform → silver.* → gold.*
```

## Getting started

### 1. Authenticate
```bash
gcloud auth login
gcloud config set project ff14-pf-data
gcloud auth application-default login
```

### 2. Enable GCP APIs
```bash
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com \
  bigquery.googleapis.com artifactregistry.googleapis.com workflows.googleapis.com \
  dataform.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
```

### 3. Configure Terraform
Create `terraform/terraform.tfvars` (gitignored):
```hcl
project_id         = "ff14-pf-data"
region             = "us-central1"
dataform_git_url   = "https://github.com/yourname/ff14-pf.git"
dataform_git_token = "ghp_xxxxxxxxxxxx"
```

### 4. Build, push, and deploy
```bash
make docker-auth          # one-time Artifact Registry login
make build-all push-all   # build + push the three service images
make deploy               # terraform apply
```

### 5. Set up Dataform credentials
```bash
cd dataform && dataform init-creds   # select BigQuery, then ADC
```

### 6. Load the worlds reference table (one-time)
See [reference/README.md](reference/README.md). In short:
```bash
gsutil cp reference/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv
bq query --nouse_legacy_sql --project_id=ff14-pf-data "$(cat reference/load_dim_worlds.sql)"
```

## Common commands

Run `make help` for the full list.

```bash
make release-scraper   # rebuild + push + run the scraper (also: release-loader, release-duty)
make run-loader        # execute a Cloud Run job ad hoc (also: run-scraper, run-duty)
make dataform-run      # dataform compile && dataform run
```

For Dataform model changes, push to `main` — the Dataform repo in GCP pulls from Git
automatically on each pipeline run.

## Disclaimer

This project scrapes publicly visible data from [xivpf.com](https://xivpf.com). Not
affiliated with Square Enix.
