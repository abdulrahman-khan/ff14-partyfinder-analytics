REGION  ?= us-central1
PROJECT ?= ff14-pf-data
REPO    := $(REGION)-docker.pkg.dev/$(PROJECT)/ff14-pf-scraper

# schema for the curated duties reference (reference/duties.csv -> bronze.raw_duties_reference)
DUTIES_SCHEMA := duty:STRING,content_category:STRING,is_savage:INTEGER,is_ultimate:INTEGER,is_unreal:INTEGER,is_extreme:INTEGER,is_high_end:INTEGER,is_alliance_raid:INTEGER,is_chaotic_alliance:INTEGER

.PHONY: help \
        build-scraper build-loader build-duty build-dataform build-all \
        push-scraper push-loader push-duty push-dataform push-all \
        release-scraper release-loader release-duty release-dataform \
        deploy run-scraper run-loader run-duty run-dataform-runner dataform-run dataform-run-gold dataform-refresh docker-auth \
        upload-duties refresh-dim-duties load-duties load-worlds run-dashboard \
        install-dev install-hooks lint test

help:
	@echo "Build:    build-scraper build-loader build-duty build-dataform build-all"
	@echo "Push:     push-scraper  push-loader  push-duty  push-dataform  push-all"
	@echo "Release:  release-scraper release-loader release-duty release-dataform  (build + push + run)"
	@echo "Run jobs: run-scraper run-loader run-duty run-dataform-runner"
	@echo "Infra:    deploy        (terraform apply)"
	@echo "Dataform: dataform-run (full compile + run) | dataform-run-gold (gold marts only, cheap) | run-dataform-runner (Cloud Run job)"
	@echo "Duties:   upload-duties (csv -> warehouse)  refresh-dim-duties (-> dim_duties)  load-duties (both)"
	@echo "Worlds:   load-worlds   (worlds.csv -> dim_worlds)"
	@echo "Dashboard: run-dashboard (streamlit summary app, local)"
	@echo "Auth:     docker-auth   (one-time Artifact Registry docker login)"
	@echo "Dev:      install-dev (dev deps) install-hooks (pre-commit) lint (ruff) test (pytest)"

docker-auth:
	gcloud auth configure-docker $(REGION)-docker.pkg.dev

# --- build images ---
build-scraper:
	docker build -t $(REPO)/scraper:latest services/scraper
build-loader:
	docker build -t $(REPO)/loader:latest services/loader
build-duty:
	docker build -t $(REPO)/duty-extractor:latest services/duty_extractor
build-dataform:
	docker build -t $(REPO)/dataform-runner:latest dataform
build-all: build-scraper build-loader build-duty build-dataform

# --- push images ---
push-scraper:
	docker push $(REPO)/scraper:latest
push-loader:
	docker push $(REPO)/loader:latest
push-duty:
	docker push $(REPO)/duty-extractor:latest
push-dataform:
	docker push $(REPO)/dataform-runner:latest
push-all: push-scraper push-loader push-duty push-dataform

# --- run Cloud Run jobs ---
run-scraper:
	gcloud run jobs execute ff14-pf-scraper --region=$(REGION)
run-loader:
	gcloud run jobs execute ff14-pf-loader --region=$(REGION)
run-duty:
	gcloud run jobs execute ff14-pf-duty-extractor --region=$(REGION)
run-dataform-runner:
	gcloud run jobs execute ff14-pf-dataform-runner --region=$(REGION)

# --- rebuild + push + run a single service ---
release-scraper:  build-scraper  push-scraper  run-scraper
release-loader:   build-loader   push-loader   run-loader
release-duty:     build-duty     push-duty     run-duty
release-dataform: build-dataform push-dataform run-dataform-runner

# --- infra + transforms ---
deploy:
	cd terraform && terraform apply

dataform-run:
	cd dataform && dataform compile && dataform run
# gold marts only (tag: gold) against existing silver - skips the pricey silver
# rebuild and the silver freshness assertion. Use after gold-only edits.
dataform-run-gold:
	cd dataform && dataform compile && dataform run --tags gold
dataform-refresh:
	cd dataform && dataform compile && dataform run --full-refresh

# --- reference data loads (edit the CSV, then run these; see reference/README.md) ---
# 1. upload reference/duties.csv into the warehouse (native bronze.raw_duties_reference; no raw-bucket write)
upload-duties:
	bq load --replace --source_format=CSV --skip_leading_rows=1 --schema="$(DUTIES_SCHEMA)" $(PROJECT):bronze.raw_duties_reference reference/duties.csv

# 2. feed the uploaded reference into dim_duties (rebuild it + everything downstream)
refresh-dim-duties:
	cd dataform && dataform run --full-refresh --actions dim_duties --include-dependents

# do both: upload the CSV and feed it into dim_duties
load-duties: upload-duties refresh-dim-duties

# worlds.csv -> GCS-backed bronze.raw_worlds external table, then rebuild dim_worlds
load-worlds:
	gsutil cp reference/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv
	bq query --nouse_legacy_sql --project_id=$(PROJECT) "$$(cat reference/load_dim_worlds.sql)"

# --- dashboard (Streamlit, local run; hosted on Streamlit Community Cloud) ---
run-dashboard:
	streamlit run services/dashboard/streamlit_app.py

# --- dev tooling ---
install-dev:
	pip install -r requirements-dev.txt
install-hooks:
	pre-commit install
lint:
	ruff check .
	ruff format --check .
test:
	pytest
