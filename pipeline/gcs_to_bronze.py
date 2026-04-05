"""
GCS → Bronze Loader
====================
Reads raw JSON files from GCS that haven't been loaded yet,
flattens the envelope, and inserts rows into bronze.raw_listings.

Run manually:   python gcs_to_bronze.py
Cloud Run Job:  triggered hourly by Cloud Scheduler (wired up later)
"""

import os
import json
import logging
from datetime import datetime, timezone

from google.cloud import storage as gcs
from google.cloud import bigquery

# -- Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# -- Settings ------------------------------------------------------------------
GCS_BUCKET  = os.environ.get("GCS_BUCKET", "ff14-pf-data-raw")
BQ_PROJECT  = os.environ.get("BQ_PROJECT", "ff14-pf-data")
BQ_DATASET  = os.environ.get("BQ_DATASET", "bronze")
BQ_TABLE    = os.environ.get("BQ_TABLE",   "raw_listings")
RAW_PREFIX  = "raw/"

# file_loads schema:
#   file_name STRING, status STRING, started_at TIMESTAMP,
#   completed_at TIMESTAMP, failed_at TIMESTAMP, error STRING


# =============================================================================
# GCS HELPERS
# =============================================================================

def list_unprocessed_files(bucket, bq_client) -> list:
    table_ref = f"`{BQ_PROJECT}.{BQ_DATASET}.file_loads`"

    query = f"""
        SELECT file_name
        FROM UNNEST(@files) AS file_name
        LEFT JOIN (
            SELECT file_name, status
            FROM {table_ref}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY file_name
                ORDER BY COALESCE(completed_at, failed_at, started_at) DESC
            ) = 1
        ) fl USING (file_name)
        WHERE fl.file_name IS NULL
           OR fl.status NOT IN ('completed')
    """

    blobs      = list(bucket.list_blobs(prefix=RAW_PREFIX))
    blob_names = [b.name for b in blobs if b.name.endswith(".json")]

    if not blob_names:
        return []

    job = bq_client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("files", "STRING", blob_names)
            ]
        ),
    )
    unprocessed_names = {row.file_name for row in job.result()}
    unprocessed = [b for b in blobs if b.name in unprocessed_names]
    log.info("Found %d new files to process", len(unprocessed))
    return unprocessed

# =============================================================================
# FILE LOAD TRACKING  (single table: file_loads)
# =============================================================================

def claim_file(bq_client, blob) -> bool:
    table = f"{BQ_PROJECT}.{BQ_DATASET}.file_loads"
    row = {
        "file_name":    blob.name,
        "status":       "processing",
        "started_at":   datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "failed_at":    None,
        "error":        None,
    }
    errors = bq_client.insert_rows_json(table, [row])
    if errors:
        log.warning("Could not claim %s: %s", blob.name, errors)
        return False
    return True

def complete_file(bq_client, blob):
    _insert_file_status(bq_client, blob.name, "completed")

def fail_file(bq_client, blob, error: Exception, context: str = ""):
    _insert_file_status(
        bq_client, blob.name, "failed",
        error=f"[{context}] {error}" if context else str(error),
    )

def _insert_file_status(bq_client, file_name: str, status: str, error: str = None):
    table = f"{BQ_PROJECT}.{BQ_DATASET}.file_loads"
    row = {
        "file_name":    file_name,
        "status":       status,
        "started_at":   None,
        "completed_at": datetime.now(timezone.utc).isoformat() if status == "completed" else None,
        "failed_at":    datetime.now(timezone.utc).isoformat() if status == "failed" else None,
        "error":        error,
    }
    errors = bq_client.insert_rows_json(table, [row])
    if errors:
        log.error("Failed to write status %s for %s: %s", status, file_name, errors)
    else:
        log.info("file_loads: %s → %s", file_name, status)


# =============================================================================
# TRANSFORM
# =============================================================================

def flatten_file(blob) -> list[dict]:
    """
    Download one GCS file and return a list of BQ-ready rows.
    Scraper envelope format:
      {
        "scraped_at":     "...",
        "listing_count":  N,
        "listings":       [ {...}, ... ]
      }
    """
    raw        = blob.download_as_text()
    payload    = json.loads(raw)
    scraped_at = payload.get("scraped_at")
    source     = f"gs://{blob.bucket.name}/{blob.name}"

    rows = []
    for item in payload.get("listings", []):
        rows.append({
            "listing_id":    item.get("listing_id"),
            "duty":          item.get("duty"),
            "category":      item.get("category"),
            "description":   item.get("description"),
            "creator":       item.get("creator"),
            "creator_server": item.get("creator_server"),
            "world":         item.get("world"),
            "min_ilvl":      item.get("min_ilvl"),
            "slots_filled":  item.get("slots_filled"),
            "slots_total":   item.get("slots_total"),
            # slot_details arrives as a list - serialise to JSON string for BQ JSON column
            "slot_details":  json.dumps(item["slot_details"]) if item.get("slot_details") else None,
            "expires_in":    item.get("expires_in"),
            "updated_at":    item.get("updated_at"),
            "scraped_at":    item.get("scraped_at") or scraped_at,
            "source_file":   source,
        })

    return rows


# =============================================================================
# BIGQUERY LOAD
# =============================================================================

def insert_rows(bq_client, rows: list[dict], blob) -> list:
    """
    Streaming insert into bronze.raw_listings.
    row_ids give BQ best-effort deduplication within a ~1 min window.
    """
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
    row_ids   = [
        f"{blob.name}:{row.get('listing_id')}:{row.get('updated_at')}"
        for row in rows
    ]
    errors = bq_client.insert_rows_json(table_ref, rows, row_ids=row_ids)
    return errors


# =============================================================================
# MAIN
# =============================================================================

def run() -> dict:
    gcs_client = gcs.Client()
    bq_client  = bigquery.Client(project=BQ_PROJECT)
    bucket     = gcs_client.bucket(GCS_BUCKET)

    files = list_unprocessed_files(bucket, bq_client)

    if not files:
        log.info("Nothing to load - exiting")
        return {"files_processed": 0, "files_failed": 0, "rows_inserted": 0}

    total_rows   = 0
    files_ok     = 0
    files_failed = 0

    for blob in files:
        log.info("Processing %s", blob.name)

        if not claim_file(bq_client, blob):
            log.info("Skipping %s (already claimed by another run)", blob.name)
            continue

        try:
            rows = flatten_file(blob)
        except Exception as e:
            log.error("Failed to parse %s: %s", blob.name, e)
            fail_file(bq_client, blob, e, context="flatten_file")
            files_failed += 1
            continue

        if not rows:
            log.warning("No rows in %s - marking complete", blob.name)
            complete_file(bq_client, blob)
            continue

        try:
            errors = insert_rows(bq_client, rows, blob)
            if errors:
                raise Exception(str(errors))
        except Exception as e:
            log.error("Failed to insert rows from %s: %s", blob.name, e)
            fail_file(bq_client, blob, e, context="insert_rows")
            files_failed += 1
            continue

        complete_file(bq_client, blob)
        total_rows += len(rows)
        files_ok   += 1
        log.info("Loaded %d rows from %s", len(rows), blob.name)

    summary = {
        "files_processed": files_ok,
        "files_failed":    files_failed,
        "rows_inserted":   total_rows,
    }
    log.info("Done: %s", summary)
    return summary


# ENTRY POINT =============================================================================

if __name__ == "__main__":
    result = run()
    print("\nDone:", result)