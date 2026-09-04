import json
from unittest.mock import MagicMock

import gcs_to_bronze as gtb
from freezegun import freeze_time


def _blob(name, bucket_name="ff14-pf-data-raw", payload=None):
    blob = MagicMock()
    blob.name = name
    blob.bucket.name = bucket_name
    if payload is not None:
        blob.download_as_text.return_value = json.dumps(payload)
    return blob


def test_flatten_file_maps_fields_and_encodes_slot_details():
    blob = _blob(
        "raw/2026/03/15/120000.json",
        payload={
            "scraped_at": "2026-03-15T12:00:00Z",
            "listings": [
                {
                    "listing_id": "abc123",
                    "duty": "Alexander",
                    "category": "Raid",
                    "description": "come",
                    "creator": "Foo",
                    "creator_server": "Faerie",
                    "world": "Faerie",
                    "min_ilvl": 700,
                    "slots_filled": 3,
                    "slots_total": 8,
                    "slot_details": [{"roles": ["dps"], "jobs": "", "filled": True}],
                    "expires_in": "10m",
                    "updated_at": "2026-03-15T11:59:00Z",
                    "scraped_at": "2026-03-15T11:58:00Z",
                }
            ],
        },
    )

    rows = gtb.flatten_file(blob)

    assert len(rows) == 1
    row = rows[0]
    assert row["listing_id"] == "abc123"
    assert row["source_file"] == "gs://ff14-pf-data-raw/raw/2026/03/15/120000.json"
    assert row["slot_details"] == json.dumps([{"roles": ["dps"], "jobs": "", "filled": True}])
    # item-level scraped_at is present, so it wins over the file-level scraped_at
    assert row["scraped_at"] == "2026-03-15T11:58:00Z"


def test_flatten_file_falls_back_to_file_level_scraped_at():
    blob = _blob(
        "raw/x.json",
        payload={
            "scraped_at": "2026-03-15T12:00:00Z",
            "listings": [{"listing_id": "abc", "slot_details": None}],
        },
    )

    rows = gtb.flatten_file(blob)

    assert rows[0]["scraped_at"] == "2026-03-15T12:00:00Z"
    assert rows[0]["slot_details"] is None


def test_flatten_file_returns_empty_list_for_no_listings():
    blob = _blob("raw/empty.json", payload={"scraped_at": "2026-03-15T12:00:00Z", "listings": []})

    assert gtb.flatten_file(blob) == []


def test_insert_rows_builds_dedup_row_ids():
    bq_client = MagicMock()
    blob = _blob("raw/x.json")
    rows = [{"listing_id": "abc", "updated_at": "2026-03-15T11:59:00Z"}]

    gtb.insert_rows(bq_client, rows, blob)

    args, kwargs = bq_client.insert_rows_json.call_args
    assert kwargs["row_ids"] == ["raw/x.json:abc:2026-03-15T11:59:00Z"]


@freeze_time("2026-03-15T12:00:00+00:00")
def test_claim_file_writes_processing_row_and_returns_true_on_success():
    bq_client = MagicMock()
    bq_client.insert_rows_json.return_value = []
    blob = _blob("raw/x.json")

    claimed = gtb.claim_file(bq_client, blob)

    assert claimed is True
    table, rows = bq_client.insert_rows_json.call_args[0]
    assert rows[0]["status"] == "processing"
    assert rows[0]["started_at"] == "2026-03-15T12:00:00+00:00"
    assert rows[0]["completed_at"] is None


def test_claim_file_returns_false_when_bq_reports_errors():
    bq_client = MagicMock()
    bq_client.insert_rows_json.return_value = [{"index": 0, "errors": ["boom"]}]
    blob = _blob("raw/x.json")

    assert gtb.claim_file(bq_client, blob) is False


def test_fail_file_includes_context_in_error_message():
    bq_client = MagicMock()
    bq_client.insert_rows_json.return_value = []
    blob = _blob("raw/x.json")

    gtb.fail_file(bq_client, blob, ValueError("bad json"), context="flatten_file")

    _, rows = bq_client.insert_rows_json.call_args[0]
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"] == "[flatten_file] bad json"
    assert rows[0]["failed_at"] is not None
    assert rows[0]["completed_at"] is None


def test_run_skips_files_claimed_by_another_run(monkeypatch):
    blob = _blob("raw/x.json")
    monkeypatch.setattr(gtb.gcs, "Client", lambda: MagicMock())
    monkeypatch.setattr(gtb.bigquery, "Client", lambda project: MagicMock())
    monkeypatch.setattr(gtb, "list_unprocessed_files", lambda bucket, bq: [blob])
    monkeypatch.setattr(gtb, "claim_file", lambda bq, b: False)
    flatten_mock = MagicMock()
    monkeypatch.setattr(gtb, "flatten_file", flatten_mock)

    result = gtb.run()

    flatten_mock.assert_not_called()
    assert result == {"files_processed": 0, "files_failed": 0, "rows_inserted": 0}


def test_run_marks_file_failed_when_flatten_raises(monkeypatch):
    blob = _blob("raw/bad.json")
    monkeypatch.setattr(gtb.gcs, "Client", lambda: MagicMock())
    monkeypatch.setattr(gtb.bigquery, "Client", lambda project: MagicMock())
    monkeypatch.setattr(gtb, "list_unprocessed_files", lambda bucket, bq: [blob])
    monkeypatch.setattr(gtb, "claim_file", lambda bq, b: True)
    monkeypatch.setattr(gtb, "flatten_file", MagicMock(side_effect=ValueError("bad json")))
    fail_mock = MagicMock()
    monkeypatch.setattr(gtb, "fail_file", fail_mock)
    insert_mock = MagicMock()
    monkeypatch.setattr(gtb, "insert_rows", insert_mock)

    result = gtb.run()

    fail_mock.assert_called_once()
    insert_mock.assert_not_called()
    assert result == {"files_processed": 0, "files_failed": 1, "rows_inserted": 0}


def test_run_completes_without_inserting_when_file_has_no_rows(monkeypatch):
    blob = _blob("raw/empty.json")
    monkeypatch.setattr(gtb.gcs, "Client", lambda: MagicMock())
    monkeypatch.setattr(gtb.bigquery, "Client", lambda project: MagicMock())
    monkeypatch.setattr(gtb, "list_unprocessed_files", lambda bucket, bq: [blob])
    monkeypatch.setattr(gtb, "claim_file", lambda bq, b: True)
    monkeypatch.setattr(gtb, "flatten_file", lambda b: [])
    complete_mock = MagicMock()
    monkeypatch.setattr(gtb, "complete_file", complete_mock)
    insert_mock = MagicMock()
    monkeypatch.setattr(gtb, "insert_rows", insert_mock)

    result = gtb.run()

    complete_mock.assert_called_once()
    insert_mock.assert_not_called()
    assert result == {"files_processed": 0, "files_failed": 0, "rows_inserted": 0}


def test_run_fails_file_when_insert_rows_returns_errors(monkeypatch):
    blob = _blob("raw/x.json")
    monkeypatch.setattr(gtb.gcs, "Client", lambda: MagicMock())
    monkeypatch.setattr(gtb.bigquery, "Client", lambda project: MagicMock())
    monkeypatch.setattr(gtb, "list_unprocessed_files", lambda bucket, bq: [blob])
    monkeypatch.setattr(gtb, "claim_file", lambda bq, b: True)
    monkeypatch.setattr(gtb, "flatten_file", lambda b: [{"listing_id": "abc"}])
    monkeypatch.setattr(gtb, "insert_rows", lambda bq, rows, b: [{"index": 0, "errors": ["x"]}])
    fail_mock = MagicMock()
    monkeypatch.setattr(gtb, "fail_file", fail_mock)
    complete_mock = MagicMock()
    monkeypatch.setattr(gtb, "complete_file", complete_mock)

    result = gtb.run()

    fail_mock.assert_called_once()
    complete_mock.assert_not_called()
    assert result == {"files_processed": 0, "files_failed": 1, "rows_inserted": 0}


def test_run_reports_success_counts_when_load_succeeds(monkeypatch):
    blob = _blob("raw/x.json")
    monkeypatch.setattr(gtb.gcs, "Client", lambda: MagicMock())
    monkeypatch.setattr(gtb.bigquery, "Client", lambda project: MagicMock())
    monkeypatch.setattr(gtb, "list_unprocessed_files", lambda bucket, bq: [blob])
    monkeypatch.setattr(gtb, "claim_file", lambda bq, b: True)
    monkeypatch.setattr(gtb, "flatten_file", lambda b: [{"listing_id": "a"}, {"listing_id": "b"}])
    monkeypatch.setattr(gtb, "insert_rows", lambda bq, rows, b: [])
    complete_mock = MagicMock()
    monkeypatch.setattr(gtb, "complete_file", complete_mock)

    result = gtb.run()

    complete_mock.assert_called_once()
    assert result == {"files_processed": 1, "files_failed": 0, "rows_inserted": 2}
