# Data Warehouse Improvement Opportunities

Based on a full end-to-end code audit of the pipeline (scraper → GCS → bronze → silver → gold).

---

## Critical

### 1. Duty difficulty detection is unverified
`dataform/definitions/silver/dim_duties.sqlx`

The `is_savage`, `is_ultimate`, `is_extreme`, `is_unreal` flags use LIKE patterns against duty names in `bronze.raw_listings`. These have never been validated against real data (flagged in `todo.md`). A silent misclassification here flows into every gold mart.

**Fix:** Run a spot-check query first:
```sql
SELECT duty, COUNT(*) AS ct
FROM bronze.raw_listings
WHERE LOWER(duty) LIKE '%(savage)%'
   OR LOWER(duty) LIKE '%(ultimate)%'
   OR LOWER(duty) LIKE '%(unreal)%'
   OR LOWER(duty) LIKE '%(extreme)%'
   OR LOWER(duty) LIKE "%(the minstrel's ballad:)%"
GROUP BY duty ORDER BY ct DESC LIMIT 50;
```
If results look wrong, replace the CASE patterns with a `duty_classifications` reference table you maintain manually.

---

### 2. No alerting on pipeline failures
Dead-letter files are written to GCS and failed file_loads records are inserted, but nothing notifies you. If the scraper starts writing dead-letters (e.g. xivpf.com changes its HTML), the pipeline silently processes zero listings indefinitely.

**Fix:** Add a Cloud Monitoring log-based metric on:
- Dead-letter writes to `gs://ff14-pf-data-raw/dead-letter/`
- Workflow step failures
- Cloud Run job failures (exit code ≠ 0)

Wire each to an alerting policy → email/PagerDuty.

---

## High Impact

### 3. `file_loads` table grows unbounded
Every 15-minute scrape adds a GCS file; every file adds at least 2 rows to `file_loads` (claim + complete). That's ~2,880 rows/day, ~1M rows/year. The loader scans the full table on every run to find unprocessed files — query cost and latency grow over time.

**Fix (two options, pick one):**
- **Partition `file_loads` by `DATE(started_at)`** and add `WHERE started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)` to the unprocessed-file query. Files older than 7 days without 'completed' status should be treated as permanently failed anyway.
- **Archive and truncate**: monthly job that moves old rows to a `file_loads_archive` table and truncates the live one.

---

### 4. No data quality assertions on business logic
Dataform asserts `nonNull` and `uniqueKey` on key fields, but there are no row-condition assertions. Silently wrong data (e.g. `slots_filled > slots_total`, negative `min_ilvl`, NULL `pf_world_key` after join) flows into gold marts undetected.

**Fix:** Add `rowConditions` assertions to `fct_listings.sqlx`:
```js
assertions: {
  nonNull: ["fct_key", "listing_id", "scraped_at", "scraped_date"],
  uniqueKey: ["listing_id", "scraped_at"],
  rowConditions: [
    "slots_filled >= 0",
    "slots_total > 0",
    "slots_filled <= slots_total",
    "min_ilvl IS NULL OR (min_ilvl > 0 AND min_ilvl < 10000)"
  ]
}
```

---

### 5. Slot detail JSON parsing fails silently
`fct_listings.sqlx` uses `JSON_QUERY_ARRAY(slot_details, '$')` to extract tank/healer/DPS counts. If `slot_details` is NULL or malformed JSON, the result is silently 0 — indistinguishable from a listing with all slots filled. This affects `open_tank_slots`, `open_healer_slots`, `open_dps_slots` in every gold mart.

**Fix:** Add a Dataform assertion or a monitoring query:
```sql
SELECT COUNT(*) AS bad_slot_details
FROM silver.fct_listings
WHERE slot_details IS NOT NULL
  AND JSON_QUERY_ARRAY(slot_details, '$') IS NULL;
```
If this is consistently non-zero, fix the serialization in `gcs_to_bronze.py`.

---

### 6. World name matching is fragile
`fct_listings.sqlx` joins `raw_listings` to `dim_worlds` via:
```sql
LOWER(TRIM(rl.world)) = LOWER(TRIM(dw.world))
```
Any variation in spelling, encoding, or trailing characters causes a NULL `pf_world_key`. This silently drops listings from datacenter-level aggregations in gold.

**Fix:** Add a monitoring query to detect unmatched worlds:
```sql
SELECT world, COUNT(*) AS ct
FROM bronze.raw_listings
WHERE LOWER(TRIM(world)) NOT IN (SELECT LOWER(TRIM(world)) FROM silver.dim_worlds)
GROUP BY world ORDER BY ct DESC;
```
If there are consistent mismatches, add a `world_aliases` table and LEFT JOIN through it.

---

## Medium Impact

### 7. `_update_file_status()` is dead code
`pipeline/gcs_to_bronze.py` — The function is defined but never called. All status changes go through `claim_file()`, `complete_file()`, and `fail_file()` instead. This causes confusion about what the intended interface is.

**Fix:** Delete `_update_file_status()` entirely.

---

### 8. Scheduler loader trigger is dead code
`terraform/scheduler.tf` has a `loader_trigger` job at `0 * * * *` that would run the loader directly. The actual loader runs via Workflows at `5 * * * *`. If the scheduler trigger fires, it runs the loader outside the orchestrated pipeline (before duty extraction, without Dataform following it).

**Fix:** Remove `loader_trigger` from `scheduler.tf` and `terraform apply`.

---

### 9. Dataform always runs against `main`
`terraform/workflows.tf` hardcodes `gitCommitish: "main"` in the Dataform compilation API call. There's no way to test Dataform changes on a feature branch without manually editing the Workflow.

**Fix:** Add a `dataform_branch` variable to Workflows (default: `"main"`) and pass it from the Scheduler trigger body or as a Workflow argument. This lets you trigger a test run with `{"dataform_branch": "feature/my-change"}`.

---

### 10. Loader processes files sequentially
`pipeline/gcs_to_bronze.py` processes one GCS file at a time. If you fall behind (e.g., after a loader outage), catching up is slow. At 15-min intervals, a 24-hour backlog = 96 files to process one-by-one.

**Fix:** Use `concurrent.futures.ThreadPoolExecutor` to process N files in parallel:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(process_file, blob): blob for blob in unprocessed}
    for future in as_completed(futures):
        ...
```
The `file_loads` insert-only pattern is already concurrency-safe.

---

### 11. `backfill.py` is not idempotent
`data/backfill.py` has no deduplication logic. Re-running it against the same SQLite database inserts duplicate rows into `bronze.raw_listings`. There's no protection beyond not running it again.

**Fix:** Either add a `source_file = 'sqlite_backfill'` filter to fct_listings deduplication logic, or add a check in backfill.py that aborts if `SELECT COUNT(*) FROM bronze.raw_listings WHERE source_file = 'sqlite_backfill'` is already > 0.

---

## Low Impact / Polish

### 12. IAM cleanup: redundant `pipeline_reader` role
`terraform/iam.tf` grants the pipeline SA both `storage.objectCreator` and `storage.objectViewer`. `objectViewer` is already implied by `objectCreator` for the pipeline's use case. Remove it to apply least-privilege.

### 13. Timezone is implicit everywhere
Python code doesn't explicitly set `timezone=UTC` on datetime objects, and SQL relies on BigQuery session defaults. This is fine today (Cloud Run defaults to UTC) but could break if the job environment changes.

**Fix:** In Python, use `datetime.now(tz=timezone.utc)` instead of `datetime.utcnow()` (deprecated in 3.12). In SQL, use `CURRENT_TIMESTAMP()` (already UTC in BigQuery) — this is already correct.

### 14. `creator_server` parsing breaks on " @ " in names
`scraper/main.py` parses `creator_server` by splitting on `" @ "`. If a player name ever contains ` @ `, parsing silently returns the wrong world. This is unlikely but worth a defensive fix:

```python
parts = creator_text.rsplit(" @ ", 1)  # rsplit limits splits from the right
creator = parts[0] if len(parts) > 1 else creator_text
creator_server = parts[1] if len(parts) > 1 else None
```

---

## Longer-Term / Future Work

### SCD Type 2 for listings
Currently, `fct_listings_deduped` keeps only the *latest* state of each listing. You lose the history of how a listing changed (e.g., description edits, slot fills over time). If fill-time modeling is a goal, you need valid_from/valid_to rows to reconstruct listing history.

### ML-ready feature store
The traveller/voyager flags, role demand columns, and duty difficulty flags were clearly designed as ML features. The next step is a feature view table joining `fct_listings` + `dim_duties` + `dim_worlds` with all engineered features in one flat table, ideally with a `time_to_fill` label derived from the last `scraped_at` before a listing disappears.

### Dataform data freshness assertions
Add a Dataform `dataAssertions` check that `MAX(scraped_at)` in `fct_listings` is within the last 2 hours. This catches cases where the pipeline is running but producing no output (e.g., loader completing but inserting 0 rows due to all files already processed).

### Looker Studio / dashboard
`todo.md` lists this. The gold layer is already structured for it — `mart_activity_hour_datacenter` maps directly to a time-series line chart, and `mart_*_by_datacenter` maps to bar charts. The main gap is connecting Looker Studio to the BigQuery gold dataset.
