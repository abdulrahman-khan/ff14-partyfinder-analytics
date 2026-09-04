import logging
import os
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BQ_PROJECT = os.environ.get("BQ_PROJECT", "ff14-pf-data")
TABLE_REF = f"{BQ_PROJECT}.bronze.raw_duties"

DUTIES_SCHEMA = [
    bigquery.SchemaField("duty", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("first_seen", "DATE", mode="NULLABLE"),
]


def get_existing_duties(bq_client):
    try:
        table = bq_client.get_table(TABLE_REF)
    except NotFound:
        log.info("raw_duties does not exist yet - will create fresh")
        return {}

    # older copies of the table predate first_seen
    has_first_seen = any(f.name == "first_seen" for f in table.schema)
    first_seen_col = "first_seen" if has_first_seen else "CAST(NULL AS DATE) AS first_seen"

    rows = bq_client.query(f"SELECT duty, {first_seen_col} FROM `{TABLE_REF}`").result()
    duties = {r.duty: (r.first_seen.isoformat() if r.first_seen else None) for r in rows}
    log.info("Found %d existing duties in raw_duties", len(duties))
    return duties


def get_bronze_duties(bq_client):
    rows = bq_client.query(f"""
        SELECT DISTINCT duty
        FROM `{BQ_PROJECT}.bronze.raw_listings`
        WHERE duty IS NOT NULL
    """).result()
    duties = {r.duty for r in rows}
    log.info("Found %d unique duties in bronze", len(duties))
    return duties


def write_duties_to_bq(bq_client, duties):
    rows = [{"duty": d, "first_seen": duties[d]} for d in sorted(duties)]
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=DUTIES_SCHEMA,
    )
    bq_client.load_table_from_json(rows, TABLE_REF, job_config=job_config).result()
    log.info("Wrote %d duties to %s", len(rows), TABLE_REF)


def run():
    bq_client = bigquery.Client(project=BQ_PROJECT)

    existing = get_existing_duties(bq_client)
    bronze = get_bronze_duties(bq_client)

    new_duties = bronze - existing.keys()
    log.info("Found %d new duties", len(new_duties))

    if not existing and not bronze:
        log.info("No duties anywhere - nothing to write")
        return {"duties_total": 0, "duties_new": 0}

    # accumulate-only: keep every duty ever seen, stamp new/legacy-null ones with today
    today = datetime.now(UTC).date().isoformat()
    merged = {d: (existing.get(d) or today) for d in (existing.keys() | bronze)}

    write_duties_to_bq(bq_client, merged)
    return {"duties_total": len(merged), "duties_new": len(new_duties)}


if __name__ == "__main__":
    print(run())
