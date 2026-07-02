REGION  ?= us-central1
PROJECT ?= ff14-pf-data
REPO    := $(REGION)-docker.pkg.dev/$(PROJECT)/ff14-pf-scraper

.PHONY: help \
        build-scraper build-loader build-duty build-all \
        push-scraper push-loader push-duty push-all \
        release-scraper release-loader release-duty \
        deploy run-scraper run-loader run-duty dataform-run docker-auth

help:
	@echo "Build:    build-scraper build-loader build-duty build-all"
	@echo "Push:     push-scraper  push-loader  push-duty  push-all"
	@echo "Release:  release-scraper release-loader release-duty  (build + push + run)"
	@echo "Run jobs: run-scraper run-loader run-duty"
	@echo "Infra:    deploy        (terraform apply)"
	@echo "Dataform: dataform-run  (compile + run)"
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
build-all: build-scraper build-loader build-duty

# --- push images ---
push-scraper:
	docker push $(REPO)/scraper:latest
push-loader:
	docker push $(REPO)/loader:latest
push-duty:
	docker push $(REPO)/duty-extractor:latest
push-all: push-scraper push-loader push-duty

# --- run Cloud Run jobs ---
run-scraper:
	gcloud run jobs execute ff14-pf-scraper --region=$(REGION)
run-loader:
	gcloud run jobs execute ff14-pf-loader --region=$(REGION)
run-duty:
	gcloud run jobs execute ff14-pf-duty-extractor --region=$(REGION)

# --- rebuild + push + run a single service ---
release-scraper: build-scraper push-scraper run-scraper
release-loader:  build-loader  push-loader  run-loader
release-duty:    build-duty    push-duty    run-duty

# --- infra + transforms ---
deploy:
	cd terraform && terraform apply

dataform-run:
	cd dataform && dataform compile && dataform run 
dataform-refresh:
	cd dataform && dataform compile && dataform run --full-refresh
