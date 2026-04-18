# FF14 Party Finder Data Warehouse — Project Handoff

## Project Overview
End-to-end GCP data engineering pipeline that scrapes FFXIV party finder listings from xivpf.com every 15 minutes, loads them into a BigQuery medallion architecture (bronze/silver/gold), and runs hourly Dataform SQL transforms. Gold layer is structured as a star schema for analytics and future ML feature engineering. Built entirely with Terraform. 1M+ historical rows backfilled from SQLite.

---

## GCP Project
- **Project ID:** `ff14-pf-data`
- **Region:** `us-central1`
- **Artifact Registry repo:** `ff14-pf-scraper`

---

## Repo Structure
```
ff14-pf/
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── terraform.tfvars        # gitignored — contains project_id, git token
│   ├── storage.tf
│   ├── artifact.tf
│   ├── iam.tf
│   ├── bigquery.tf
│   ├── bigquery_worlds.tf      # external table for bronze.worlds
│   ├── cloud_run.tf            # scraper + loader + duty-extractor jobs
│   ├── scheduler.tf            # scraper (*/15) + pipeline (5 * * * *)
│   ├── workflows.tf            # Cloud Workflows orchestration
│   └── dataform.tf             # Dataform repo + git connection (google-beta provider)
├── scraper/
│   ├── main.py                 # xivpf.com scraper → GCS
│   └── Dockerfile
├── pipeline/
│   ├── gcs_to_bronze.py        # GCS → bronze.raw_listings loader
│   └── Dockerfile
├── duty_extractor/
│   ├── extract_duties.py       # bronze → duties.csv → bronze.duties
│   └── Dockerfile
├── dataform/
│   ├── workflow_settings.yaml
│   └── definitions/
│       ├── bronze/
│       │   ├── raw_listings.sqlx       # declaration stub
│       │   ├── worlds.sqlx             # declaration stub
│       │   └── duties.sqlx             # declaration stub
│       ├── silver/
│       │   ├── listings_clean.sqlx     # main silver transform
│       │   └── worlds_clean_decl.sqlx  # declaration stub (managed manually)
│       └── gold/
│           ├── dim_worlds.sqlx         # world reference dim
│           ├── dim_duties.sqlx         # duty reference dim with difficulty flags
│           ├── fct_listings.sqlx       # core fact table
│           ├── duty_stats.sqlx         # hourly aggregates
│           └── role_demand.sqlx        # role scarcity aggregates
├── scripts/
│   └── load_worlds_clean.sql   # one-time script to materialize silver.worlds_clean
└── data/
    └── worlds.csv              # world → datacenter → region reference (not committed)
```

---

## Docker Image Commands

```bash
# configure docker auth (run once)
gcloud auth configure-docker us-central1-docker.pkg.dev

# scraper
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest ./scraper
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/scraper:latest

# loader
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest ./pipeline
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/loader:latest

# duty extractor
docker build -t us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/duty-extractor:latest ./duty_extractor
docker push us-central1-docker.pkg.dev/ff14-pf-data/ff14-pf-scraper/duty-extractor:latest
```

---

## Pipeline Flow

```
xivpf.com
    ↓ every 15 min — Cloud Scheduler → Cloud Run (scraper)
GCS: raw/YYYY/MM/DD/HHMMSS.json
    ↓ every hour at :05 — Cloud Scheduler → Cloud Workflows
    ├── Cloud Run (duty-extractor) → reference_data/duties.csv → bronze.duties
    ├── wait 30s
    ├── Cloud Run (loader) → bronze.raw_listings
    ├── wait 120s
    └── Dataform
            ├── silver.listings_clean    (incremental)
            ├── gold.dim_worlds          (table — rebuilds every run)
            ├── gold.dim_duties          (table — rebuilds every run)
            ├── gold.fct_listings        (incremental)
            ├── gold.duty_stats          (incremental)
            └── gold.role_demand         (incremental)
```

---

## Service Accounts
- `ff14-pf-scraper` — scraper job: GCS objectCreator + secretmanager accessor
- `ff14-pf-pipeline` — loader + workflows + dataform: GCS objectViewer + objectCreator, BQ dataEditor + jobUser, workflows invoker, dataform editor

---

## BigQuery Schema

### bronze.raw_listings
Partitioned by `scraped_at` (DAY).
| column | type |
|---|---|
| listing_id | STRING |
| duty | STRING |
| category | STRING |
| description | STRING |
| creator | STRING |
| creator_server | STRING |
| world | STRING |
| min_ilvl | INTEGER |
| slots_filled | INTEGER |
| slots_total | INTEGER |
| slot_details | JSON |
| expires_in | STRING |
| updated_at | STRING |
| scraped_at | TIMESTAMP |
| source_file | STRING |

### bronze.file_loads
Tracks loader state per GCS file. Insert-only — no DML.
| column | type |
|---|---|
| file_name | STRING |
| status | STRING (`processing` / `completed` / `failed`) |
| started_at | TIMESTAMP |
| completed_at | TIMESTAMP |
| failed_at | TIMESTAMP |
| error | STRING |

### bronze.failed_files
| column | type |
|---|---|
| file_name | STRING |
| failed_at | TIMESTAMP |
| error | STRING |
| context | STRING |

### bronze.duties
Populated by duty extractor. Only updated when new duties found.
| column | type |
|---|---|
| duty | STRING |

### bronze.worlds (external table)
Points at `gs://ff14-pf-data-raw/worlds_data/worlds.csv`.

### silver.worlds_clean
Managed manually via `scripts/load_worlds_clean.sql`. Not in Dataform DAG. Declared as stub so Dataform can ref() it.
| column | type |
|---|---|
| world | STRING |
| datacenter | STRING |
| region | STRING |

### silver.listings_clean
Partitioned by `scraped_at` (DAY). Clustered by `pf_world`, `duty`, `scraped_date`.
| column | type | notes |
|---|---|---|
| listing_id | STRING | |
| duty | STRING | |
| is_savage | INTEGER | derived from duty name |
| is_ultimate | INTEGER | derived from duty name |
| is_unreal | INTEGER | derived from duty name |
| is_extreme | INTEGER | derived from duty name |
| is_cross | INTEGER | 1 if cross-world listing |
| category | STRING | raw category value |
| description_clean | STRING | [tags] stripped |
| is_loot | INTEGER | |
| is_practice | INTEGER | |
| is_clear | INTEGER | |
| is_one_per_job | INTEGER | |
| is_weekly_unclaimed | INTEGER | |
| is_duty_completion | INTEGER | |
| is_duty_complete | INTEGER | |
| is_duty_incomplete | INTEGER | |
| creator_name | STRING | |
| creator_world | STRING | |
| creator_datacenter | STRING | joined from worlds_clean |
| creator_region | STRING | joined from worlds_clean |
| pf_world | STRING | world listing is posted on |
| pf_datacenter | STRING | joined from worlds_clean |
| pf_region | STRING | joined from worlds_clean |
| is_traveller | INTEGER | creator DC ≠ pf DC |
| is_voyager | INTEGER | creator region ≠ pf region |
| min_ilvl | INTEGER | |
| slots_filled | INTEGER | |
| slots_total | INTEGER | |
| slots_open | INTEGER | |
| scraped_at | TIMESTAMP | |
| scraped_date | DATE | |
| scraped_time | TIME | |
| open_tank_slots | INTEGER | derived from slot_details JSON |
| open_healer_slots | INTEGER | derived from slot_details JSON |
| open_dps_slots | INTEGER | derived from slot_details JSON |

### gold.dim_worlds
| column | type |
|---|---|
| world_key | STRING (MD5 surrogate) |
| world | STRING |
| datacenter | STRING |
| region | STRING |

### gold.dim_duties
| column | type |
|---|---|
| duty_key | STRING (MD5 surrogate) |
| duty | STRING |
| is_savage | INTEGER |
| is_ultimate | INTEGER |
| is_unreal | INTEGER |
| is_extreme | INTEGER |
| is_high_end | INTEGER |

### gold.fct_listings
Partitioned by `scraped_date`. Clustered by `pf_world_key`, `duty_key`, `scraped_date`.
| column | type |
|---|---|
| fct_key | STRING (MD5 surrogate) |
| duty_key | STRING → dim_duties |
| pf_world_key | STRING → dim_worlds |
| creator_world_key | STRING → dim_worlds |
| listing_id | STRING |
| duty | STRING |
| pf_world | STRING |
| creator_world | STRING |
| is_traveller | INTEGER |
| is_voyager | INTEGER |
| is_cross | INTEGER |
| is_loot | INTEGER |
| is_practice | INTEGER |
| is_clear | INTEGER |
| is_one_per_job | INTEGER |
| is_weekly_unclaimed | INTEGER |
| is_duty_completion | INTEGER |
| is_duty_complete | INTEGER |
| is_duty_incomplete | INTEGER |
| description_clean | STRING |
| min_ilvl | INTEGER |
| slots_filled | INTEGER |
| slots_total | INTEGER |
| slots_open | INTEGER |
| open_tank_slots | INTEGER |
| open_healer_slots | INTEGER |
| open_dps_slots | INTEGER |
| scraped_at | TIMESTAMP |
| scraped_date | DATE |
| scraped_time | TIME |

### gold.duty_stats
Partitioned by `date` (DAY).
| column | type |
|---|---|
| duty | STRING |
| is_cross | INTEGER |
| pf_world | STRING |
| pf_datacenter | STRING |
| pf_region | STRING |
| date | DATE |
| hour | INTEGER |
| listing_count | INTEGER |
| avg_party_size | FLOAT |
| avg_min_ilvl | FLOAT |
| listings_needing_tank | INTEGER |
| listings_needing_healer | INTEGER |
| listings_needing_dps | INTEGER |
| avg_fill_rate_pct | FLOAT |

### gold.role_demand
Partitioned by `date` (DAY).
| column | type |
|---|---|
| duty | STRING |
| is_cross | INTEGER |
| pf_world | STRING |
| pf_datacenter | STRING |
| pf_region | STRING |
| date | DATE |
| hour | INTEGER |
| total_listings | INTEGER |
| total_open_tank | INTEGER |
| total_open_healer | INTEGER |
| total_open_dps | INTEGER |
| most_wanted_role | STRING |

---

## Key Design Decisions

**GCS as landing zone** — scraper writes raw JSON, loader handles BQ concerns separately. Raw data never lost if loader breaks.

**Insert-only file_loads** — BQ streaming buffer blocks DML on recently inserted rows. All status changes are new inserts, latest status resolved with `QUALIFY ROW_NUMBER()`.

**silver.worlds_clean managed manually** — static 3-column reference table. Created once via `scripts/load_worlds_clean.sql`, declared as a stub in Dataform so it can be ref()'d. Removed from Terraform to avoid conflicts.

**Star schema in gold** — `fct_listings` keyed to `dim_duties` and `dim_worlds`. Difficulty flags live in `dim_duties` not on every fact row. Two foreign keys to `dim_worlds` (pf side + creator side).

**category dropped** — replaced with `is_cross` boolean. Only meaningful signal was cross vs not-cross.

**Traveller/voyager** — ML features for future fill-time prediction. `is_traveller` = creator DC ≠ pf DC. `is_voyager` = creator region ≠ pf region.

**Duty extractor** — runs before the loader in Workflows. Queries bronze for unique duties, appends new ones to `duties.csv` in GCS, loads into `bronze.duties`. Skips GCS and BQ write entirely if no new duties found.

---

## Manual Run Commands

```bash
# trigger jobs
gcloud run jobs execute ff14-pf-scraper --region=us-central1
gcloud run jobs execute ff14-pf-duty-extractor --region=us-central1
gcloud run jobs execute ff14-pf-loader --region=us-central1

# check logs
gcloud run jobs executions list --job=ff14-pf-loader --region=us-central1

# verify row counts
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM bronze.raw_listings"
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM silver.listings_clean"
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM gold.fct_listings"
bq query --nouse_legacy_sql "SELECT COUNT(*) FROM bronze.duties"

# dataform
dataform compile
dataform run
dataform run --full-refresh
```

---

## Known Issues / Watch Points
- `silver.worlds_clean` not managed by Terraform — if deleted, rerun `scripts/load_worlds_clean.sql`
- `_update_file_status()` is dead code in `gcs_to_bronze.py` — can be deleted
- `pipeline_reader` (objectViewer) on pipeline SA is redundant alongside `pipeline_writer` — harmless but can be cleaned up
- CASE statement patterns in `dim_duties` for duty difficulty not confirmed working yet — need to verify against actual duty name formats in bronze

---

## What's Left To Do
- [ ] Verify dim_duties CASE statements match actual duty name formats in bronze
- [ ] Looker Studio dashboard connected to gold tables
- [ ] BigQuery ML — clustering on job compositions, fill-time regression
- [ ] SCD Type 2 on silver — track listing changes between scrapes
- [ ] Dataform assertions — data quality checks
- [ ] Cloud Monitoring alerts on job failures
- [ ] README architecture diagram
