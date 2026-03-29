"""
SQLite → BigQuery historical backfill
======================================
One-time script to load existing SQLite data into bronze.raw_listings.
Run locally: python backfill.py
"""

import sqlite3
import json
import logging
from datetime import timezone, datetime

from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

SQLITE_FILE = "xivpf.db"
BQ_PROJECT  = "ff14-pf-data"
BQ_DATASET  = "bronze"
BQ_TABLE    = "raw_listings"
BATCH_SIZE  = 500   # BQ streaming insert max is 50MB / 50k rows per request — 500 is safe

def convert_row(row: sqlite3.Row) -> dict:
    # slot_details is already a JSON string in SQLite — pass through as-is
    slot_details = row["slot_details"]
    if slot_details:
        try:
            # validate it parses, then re-dump cleanly
            slot_details = json.dumps(json.loads(slot_details))
        except (json.JSONDecodeError, TypeError):
            slot_details = None

    # SQLite timestamps are strings — normalize to ISO format for BQ TIMESTAMP
    def to_iso(ts):
        if not ts:
            return None
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") \
                           .replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None

    return {
        "listing_id":    row["listing_id"],
        "duty":          row["duty"],
        "category":      row["category"],
        "description":   row["description"],
        "creator":       row["creator"],
        "creator_server": row["creator_server"],
        "world":         row["world"],
        "min_ilvl":      row["min_ilvl"],
        "slots_filled":  row["slots_filled"],
        "slots_total":   row["slots_total"],
        "slot_details":  slot_details,
        "expires_in":    row["expires_in"],
        "updated_at":    row["updated_at"],
        "scraped_at":    to_iso(row["last_seen"]),   # use last_seen as scraped_at
        "source_file":   "sqlite_backfill",
    }


def run():
    bq_client = bigquery.Client(project=BQ_PROJECT)
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

    conn = sqlite3.connect(SQLITE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pf_listings")
    total = cursor.fetchone()[0]
    log.info("Total rows in SQLite: %d", total)

    cursor.execute("SELECT * FROM pf_listings ORDER BY id ASC")

    batch       = []
    inserted    = 0
    failed      = 0
    batch_count = 0

    for row in cursor:
        try:
            batch.append(convert_row(row))
        except Exception as e:
            log.warning("Failed to convert row id=%s: %s", row["id"], e)
            failed += 1
            continue

        if len(batch) >= BATCH_SIZE:
            errors = bq_client.insert_rows_json(table_ref, batch)
            if errors:
                log.error("Batch %d insert errors: %s", batch_count, errors[:2])
                failed += len(batch)
            else:
                inserted += len(batch)

            batch_count += 1
            batch = []

            if batch_count % 20 == 0:
                log.info("Progress: %d / %d rows inserted", inserted, total)

    # flush final partial batch
    if batch:
        errors = bq_client.insert_rows_json(table_ref, batch)
        if errors:
            log.error("Final batch insert errors: %s", errors[:2])
            failed += len(batch)
        else:
            inserted += len(batch)

    conn.close()
    log.info("Done. Inserted: %d, Failed: %d, Total: %d", inserted, failed, total)


if __name__ == "__main__":
    run()