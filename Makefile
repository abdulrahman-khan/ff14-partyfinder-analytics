REGION  ?= us-central1
PROJECT ?= ff14-pf-data
REPO    := $(REGION)-docker.pkg.dev/$(PROJECT)/ff14-pf-scraper

.PHONY: help \
        build-scraper build-loader build-duty build-dataform build-all \
        push-scraper push-loader push-duty push-dataform push-all \
        release-scraper release-loader release-duty release-dataform \
        deploy run-scraper run-loader run-duty run-dataform-runner dataform-run docker-auth

help:
	@echo "Build:    build-scraper build-loader build-duty build-dataform build-all"
	@echo "Push:     push-scraper  push-loader  push-duty  push-dataform  push-all"
	@echo "Release:  release-scraper release-loader release-duty release-dataform  (build + push + run)"
	@echo "Run jobs: run-scraper run-loader run-duty run-dataform-runner"
	@echo "Infra:    deploy        (terraform apply)"
	@echo "Dataform: dataform-run  (local compile + run)  |  run-dataform-runner (Cloud Run job)"
	@echo "Auth:     docker-auth   (one-time Artifact Registry docker login)"

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
dataform-refresh:
	cd dataform && dataform compile && dataform run --full-refresh
