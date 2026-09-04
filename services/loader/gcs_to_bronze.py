import json
import logging
import os
from datetime import UTC, datetime

from google.cloud import bigquery
from google.cloud import storage as gcs
from google.cloud.workflows.executions_v1 import ExecutionsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GCS_BUCKET = os.environ.get("GCS_BUCKET", "ff14-pf-data-raw")
BQ_PROJECT = os.environ.get("BQ_PROJECT", "ff14-pf-data")
BQ_DATASET = os.environ.get("BQ_DATASET", "bronze")
BQ_TABLE = os.environ.get("BQ_TABLE", "raw_listings")
RAW_PREFIX = "raw/"

# duty-extractor -> Dataform pipeline, kicked off after a successful load
REGION = os.environ.get("REGION", "us-central1")
WORKFLOW_NAME = os.environ.get("WORKFLOW_NAME", "ff14-pf-pipeline")


def list_unprocessed_files(bucket, bq_client):
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

    blobs = list(bucket.list_blobs(prefix=RAW_PREFIX))
    blob_names = [b.name for b in blobs if b.name.endswith(".json")]
    if not blob_names:
        return []

    job = bq_client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("files", "STRING", blob_names)]
        ),
    )
    unprocessed_names = {row.file_name for row in job.result()}
    unprocessed = [b for b in blobs if b.name in unprocessed_names]
    log.info("Found %d new files to process", len(unprocessed))
    return unprocessed


# file_loads is insert-only; a file's current status is its latest row.
def claim_file(bq_client, blob):
    table = f"{BQ_PROJECT}.{BQ_DATASET}.file_loads"
    row = {
        "file_name": blob.name,
        "status": "processing",
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "failed_at": None,
        "error": None,
    }
    errors = bq_client.insert_rows_json(table, [row])
    if errors:
        log.warning("Could not claim %s: %s", blob.name, errors)
        return False
    return True


def complete_file(bq_client, blob):
    _insert_file_status(bq_client, blob.name, "completed")


def fail_file(bq_client, blob, error, context=""):
    _insert_file_status(
        bq_client,
        blob.name,
        "failed",
        error=f"[{context}] {error}" if context else str(error),
    )


def _insert_file_status(bq_client, file_name, status, error=None):
    table = f"{BQ_PROJECT}.{BQ_DATASET}.file_loads"
    now = datetime.now(UTC).isoformat()
    row = {
        "file_name": file_name,
        "status": status,
        "started_at": None,
        "completed_at": now if status == "completed" else None,
        "failed_at": now if status == "failed" else None,
        "error": error,
    }
    errors = bq_client.insert_rows_json(table, [row])
    if errors:
        log.error("Failed to write status %s for %s: %s", status, file_name, errors)
    else:
        log.info("file_loads: %s -> %s", file_name, status)


def flatten_file(blob):
    payload = json.loads(blob.download_as_text())
    scraped_at = payload.get("scraped_at")
    source = f"gs://{blob.bucket.name}/{blob.name}"

    rows = []
    for item in payload.get("listings", []):
        rows.append(
            {
                "listing_id": item.get("listing_id"),
                "duty": item.get("duty"),
                "category": item.get("category"),
                "description": item.get("description"),
                "creator": item.get("creator"),
                "creator_server": item.get("creator_server"),
                "world": item.get("world"),
                "min_ilvl": item.get("min_ilvl"),
                "slots_filled": item.get("slots_filled"),
                "slots_total": item.get("slots_total"),
                "slot_details": json.dumps(item["slot_details"])
                if item.get("slot_details")
                else None,
                "expires_in": item.get("expires_in"),
                "updated_at": item.get("updated_at"),
                "scraped_at": item.get("scraped_at") or scraped_at,
                "source_file": source,
            }
        )
    return rows


def insert_rows(bq_client, rows, blob):
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
    # row_ids give BQ best-effort dedup within a ~1 min window
    row_ids = [f"{blob.name}:{r.get('listing_id')}:{r.get('updated_at')}" for r in rows]
    return bq_client.insert_rows_json(table_ref, rows, row_ids=row_ids)


def run():
    gcs_client = gcs.Client()
    bq_client = bigquery.Client(project=BQ_PROJECT)
    bucket = gcs_client.bucket(GCS_BUCKET)

    files = list_unprocessed_files(bucket, bq_client)
    if not files:
        log.info("Nothing to load - exiting")
        return {"files_processed": 0, "files_failed": 0, "rows_inserted": 0}

    total_rows = 0
    files_ok = 0
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
        files_ok += 1
        log.info("Loaded %d rows from %s", len(rows), blob.name)

    summary = {
        "files_processed": files_ok,
        "files_failed": files_failed,
        "rows_inserted": total_rows,
    }
    log.info("Done: %s", summary)
    return summary


def trigger_pipeline():
    # refreshes silver/gold after a load; a failure here doesn't fail the load
    parent = f"projects/{BQ_PROJECT}/locations/{REGION}/workflows/{WORKFLOW_NAME}"
    try:
        execution = ExecutionsClient().create_execution(parent=parent)
        log.info("Triggered pipeline workflow: %s", execution.name)
    except Exception as e:
        log.error("Load succeeded but failed to trigger pipeline workflow %s: %s", parent, e)


if __name__ == "__main__":
    result = run()
    trigger_pipeline()
    print(result)
