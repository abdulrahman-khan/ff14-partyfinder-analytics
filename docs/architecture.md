# Architecture

End-to-end GCP data pipeline that scrapes FFXIV Party Finder listings from
[xivpf.com](https://xivpf.com) every 15 minutes, stores them in BigQuery via a medallion
architecture (bronze → silver → gold), and runs hourly SQL transforms with Dataform.
Infrastructure is fully managed with Terraform.

- **GCP project:** `ff14-pf-data`
- **Region:** `us-central1`

This is the canonical reference for repo layout, data flow, and schema. For the gold marts
and the lifecycle model see [`gold_marts.md`](gold_marts.md); for the failure-alerting and
logging setup see [`observability.md`](observability.md); for the open backlog see
[`improvements.md`](improvements.md).

---

## Repository layout

```
ff14-pf/
├── Makefile               # build / push / deploy / run commands
├── services/              # Python Cloud Run jobs (ingestion)
│   ├── scraper/           #   xivpf.com HTML → JSON in GCS
│   ├── loader/            #   GCS JSON → bronze.raw_listings
│   └── duty_extractor/    #   distinct duties → bronze.duties
├── dataform/              # SQL transforms (bronze/silver/gold + includes)
│   └── definitions/{bronze,silver,gold}/
├── terraform/             # all infrastructure, one file per concern
├── reference/             # static reference data + its loaders (worlds.csv, load_dim_worlds.sql)
├── tools/                 # one-off / local utilities (backfill.py, xivpf.db)
└── docs/                  # architecture, gold marts, observability, improvements
```

---

## Data flow

```
xivpf.com
  ↓ Cloud Scheduler (every 15 min)
Cloud Run: scraper → GCS: gs://ff14-pf-data-raw/raw/YYYY/MM/DD/HHMMSS.json
  ↓ Cloud Scheduler → Cloud Workflows (hourly at :05)
  ├─ Cloud Run: duty-extractor → bronze.duties
  ├─ +30s: Cloud Run: loader → bronze.raw_listings
  └─ +150s: Dataform → silver.* → gold.*
```

| Source dir | Cloud Run job | Purpose |
|---|---|---|
| `services/scraper/` | `ff14-pf-scraper` | HTML-parse xivpf.com → JSON to GCS |
| `services/loader/` | `ff14-pf-loader` | GCS JSON → `bronze.raw_listings` |
| `services/duty_extractor/` | `ff14-pf-duty-extractor` | Extract distinct duties → `bronze.duties` |

---

## Medallion layers

### Bronze (`dataform/definitions/bronze/`) — raw ingestion, append-only
- `raw_listings` — partitioned by `scraped_at` (DAY).
- `file_loads` — GCS file-processing tracker; **insert-only** (see design decisions).
- `duties` — distinct duty names from raw_listings.
- `raw_worlds` — external table over `reference/worlds.csv` in GCS.
- `dim_players` — **identity vault**; one row per `player_hash` mapping it to the real
  character name + home world. The only table where a name is recoverable; bronze-restricted
  by IAM (see design decisions).

### Silver (`dataform/definitions/silver/`) — cleaned, keyed, flagged
- `fct_listings` — **periodic snapshot fact**; one row per listing per scrape. Incremental
  on `scraped_at`, partitioned by `scraped_date`, clustered by
  `pf_world_key / duty_key / scraped_date`. Carries pseudonymous `player_hash` +
  `creator_initials` only — the real creator name never leaves bronze.
- `fct_listing_lifecycle` — **accumulating snapshot fact**; one row per listing *session*
  (gap-and-islands sessionized). Derives lifetime, time-to-fill, fill outcome, role
  bottleneck. Incremental merge on `[listing_id, session_start]` with a 3-day lookback. The
  keystone for every gold mart — see [`gold_marts.md`](gold_marts.md).
- `dim_duties` — difficulty flags + `content_category` via CASE on duty name.
- `dim_date` — calendar dimension with FFXIV reset-week (Tuesday 08:00 UTC) attributes.
- `dim_worlds` — **stub declaration only**; the real table is built manually via
  `reference/load_dim_worlds.sql` (see [`reference/README.md`](../reference/README.md)).
- `fct_listings_deduped` — deduplicated view of `fct_listings` (latest snapshot per listing).
- `assert_lifecycle_freshness` — assertion: fails if the newest session is > 3h old.
- `qa_unmatched_worlds` — non-blocking monitoring view: worlds in raw_listings not matched
  in dim_worlds.

### Gold (`dataform/definitions/gold/`) — pre-aggregated, chart-ready marts
Region is a dimension, never hardcoded. All marts source from `fct_listing_lifecycle`.
- `mart_time_to_fill` — **hero**; median/p90 time-to-fill + fill rate by duty × region × DC
  × weekday × hour.
- `mart_role_demand` — open-slot shares + bottleneck role by content × region × DC × hour.
- `mart_activity_heatmap` — posting activity by region × DC × weekday × hour.
- `mart_content_trends` — week-over-week listing volume + `wow_pct_change` + weekly rank per
  duty/region.
- `mart_traveller_flow` — per-DC inbound/outbound/net travel flow.

Full mart catalog, grains, and the lifecycle model are in [`gold_marts.md`](gold_marts.md).
Shared logic (`resetWeekBounds` / `resetWeekStart` macros, `SESSION_GAP_MIN`,
`playerHash` / `playerInitials`) lives in `dataform/includes/ffxiv.js`.

---

## Non-obvious design decisions

**`file_loads` is insert-only.** BigQuery's streaming insert buffer blocks DML on
recently-inserted rows. Status updates are written as new rows; current status is resolved at
query time with `QUALIFY ROW_NUMBER() OVER (PARTITION BY file_path ORDER BY updated_at DESC) = 1`.

**`silver.dim_worlds` is not managed by Dataform or Terraform.** It is a static reference
table created once via `reference/load_dim_worlds.sql` and declared as a stub in Dataform so
other models can `ref('dim_worlds')`. Do not recreate it through Dataform.

**Surrogate keys are MD5 hashes** of natural keys (duty name, world name) for dimensional
consistency across bronze/silver/gold joins.

**Player identity is pseudonymized at the bronze→silver boundary.** `bronze.raw_listings`
still holds the real creator name (raw capture), but everything downstream carries only
`player_hash` = `TO_HEX(MD5(lower(creator) | lower(creator_server)))`
(firstname+lastname+homeserver) and display `creator_initials` (`M. L.`). Only
`bronze.dim_players` maps a hash back to a name. The boundary is enforced by BigQuery IAM, not
convention: the `analyst_group` variable grants `dataViewer` on **silver + gold only**, while
`bronze_reader_group` grants bronze to trusted devs. Hash/initials logic is centralized in
`ffxiv.playerHash` / `ffxiv.playerInitials`. Caveat: `description_clean` is free text and may
still contain names a user typed — out of scope here (tracked in `improvements.md`).

**Traveller/voyager flags** (`is_traveller`, `is_voyager`) derive from datacenter/region
mismatches between `creator_world_key` and `pf_world_key` — intentional features for future
ML analysis.

**`listing_id`** is a SHA1 hash of `(creator, duty, description)` generated in the scraper,
enabling deduplication across scrape windows.

**Listing sessionization (gap-and-islands).** Because `listing_id` is content-hashed, an
identical re-post weeks later collides to the same id. `fct_listing_lifecycle` splits the
snapshot stream into sessions whenever consecutive scrapes are more than `SESSION_GAP_MIN`
(30 min) apart, keying each session by `(listing_id, session_start)`. Time-to-fill caveats
(±15 min resolution, description edits, right-censored single-snapshot "flash" sessions) are
documented in that model's `description`.

**`slot_details`** is stored as a JSON string in BigQuery and parsed in `fct_listings.sqlx`
to extract `open_tank_slots`, `open_healer_slots`, `open_dps_slots`.

---

## Dataform configuration

`dataform/workflow_settings.yaml`: default dataset `silver`, default project `ff14-pf-data`,
default location `us-central1`, core version `3.0.0`. Dataform is git-synced to this repo via
a GitHub PAT stored in Secret Manager.

## Hard rule

**Never modify the raw data GCS bucket (`gs://ff14-pf-data-raw`).** It is the source of truth
for all raw scraped data — do not delete, overwrite, move, or alter any objects in it under
any circumstances.
