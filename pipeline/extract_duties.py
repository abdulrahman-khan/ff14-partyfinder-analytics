"""
Bronze → Duty Reference Extractor

appends new duty names to duties.csv in GCS
then loads full file into bronze.duties
"""

import os
import io
import csv
import logging
from datetime import datetime, timezone

from google.cloud import storage as gcs
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

GCS_BUCKET    = os.environ.get("GCS_BUCKET",    "ff14-pf-data-raw")
BQ_PROJECT    = os.environ.get("BQ_PROJECT",    "ff14-pf-data")
DUTIES_PATH   = "reference_data/duties.csv"


def get_existing_duties(bucket) -> set:
    """Read existing duties from GCS CSV, return as a set."""
    blob = bucket.blob(DUTIES_PATH)
    if not blob.exists():
        log.info("No existing duties.csv found — will create fresh")
        return set()

    content = blob.download_as_text()
    reader  = csv.DictReader(io.StringIO(content))
    duties  = {row["duty"] for row in reader}
    log.info("Found %d existing duties in GCS", len(duties))
    return duties


def get_bronze_duties(bq_client) -> set:
    """Query bronze for all unique duty names."""
    query = f"""
        SELECT DISTINCT duty
        FROM `{BQ_PROJECT}.bronze.raw_listings`
        WHERE duty IS NOT NULL
    """
    results = bq_client.query(query).result()
    duties  = {row.duty for row in results}
    log.info("Found %d unique duties in bronze", len(duties))
    return duties


def write_duties_to_gcs(bucket, duties: set):
    """Write full duty list to GCS as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["duty", "first_seen"])
    writer.writeheader()
    for duty in sorted(duties):
        writer.writerow({
            "duty":       duty,
            "first_seen": datetime.now(timezone.utc).date().isoformat(),
        })

    blob = bucket.blob(DUTIES_PATH)
    blob.upload_from_string(output.getvalue(), content_type="text/csv")
    log.info("Wrote %d duties to gs://%s/%s", len(duties), GCS_BUCKET, DUTIES_PATH)


def load_duties_to_bq(bq_client, bucket):
    """Load duties CSV from GCS into bronze.duties via load job."""
    uri       = f"gs://{GCS_BUCKET}/{DUTIES_PATH}"
    table_ref = f"{BQ_PROJECT}.bronze.duties"

    job_config = bigquery.LoadJobConfig(
        source_format        = bigquery.SourceFormat.CSV,
        skip_leading_rows    = 1,
        write_disposition    = bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema = [
            bigquery.SchemaField("duty",       "STRING", mode="REQUIRED"),
            bigquery.SchemaField("first_seen", "DATE",   mode="NULLABLE"),
        ],
    )

    load_job = bq_client.load_table_from_uri(uri, table_ref, job_config=job_config)
    load_job.result()
    log.info("Loaded duties into %s", table_ref)


def run() -> dict:
    gcs_client = gcs.Client()
    bq_client  = bigquery.Client(project=BQ_PROJECT)
    bucket     = gcs_client.bucket(GCS_BUCKET)

    existing_duties = get_existing_duties(bucket)
    bronze_duties   = get_bronze_duties(bq_client)

    new_duties = bronze_duties - existing_duties
    log.info("Found %d new duties to append", len(new_duties))

    if not new_duties and existing_duties:
        log.info("No new duties — skipping write")
        return {"duties_total": len(existing_duties), "duties_new": 0}

    all_duties = existing_duties | bronze_duties
    write_duties_to_gcs(bucket, all_duties)
    load_duties_to_bq(bq_client, bucket)

    return {"duties_total": len(all_duties), "duties_new": len(new_duties)}


if __name__ == "__main__":
    result = run()
    print("\nDone:", result)