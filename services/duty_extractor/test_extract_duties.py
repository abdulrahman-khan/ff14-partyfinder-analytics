from unittest.mock import MagicMock

import extract_duties as ed
from freezegun import freeze_time
from google.api_core.exceptions import NotFound


def _row(duty, first_seen=None):
    r = MagicMock()
    r.duty = duty
    r.first_seen = first_seen
    return r


def test_get_existing_duties_returns_empty_dict_when_table_missing():
    bq_client = MagicMock()
    bq_client.get_table.side_effect = NotFound("no table")

    result = ed.get_existing_duties(bq_client)

    assert result == {}
    bq_client.query.assert_not_called()


def test_get_existing_duties_reads_first_seen_when_column_present():
    bq_client = MagicMock()
    field = MagicMock()
    field.name = "first_seen"
    bq_client.get_table.return_value.schema = [field]
    bq_client.query.return_value.result.return_value = [
        _row("Aloalo Island", first_seen=MagicMock(isoformat=lambda: "2026-01-01")),
        _row("Alexander", first_seen=None),
    ]

    result = ed.get_existing_duties(bq_client)

    assert result == {"Aloalo Island": "2026-01-01", "Alexander": None}
    query_sql = bq_client.query.call_args[0][0]
    assert "first_seen" in query_sql
    assert "CAST(NULL AS DATE)" not in query_sql


def test_get_existing_duties_falls_back_to_null_first_seen_on_legacy_table():
    bq_client = MagicMock()
    bq_client.get_table.return_value.schema = []  # no first_seen column

    ed.get_existing_duties(bq_client)

    query_sql = bq_client.query.call_args[0][0]
    assert "CAST(NULL AS DATE) AS first_seen" in query_sql


def test_get_bronze_duties_returns_distinct_set():
    bq_client = MagicMock()
    bq_client.query.return_value.result.return_value = [_row("Alexander"), _row("Alexander")]

    result = ed.get_bronze_duties(bq_client)

    assert result == {"Alexander"}


def test_write_duties_to_bq_sorts_rows_and_truncates():
    bq_client = MagicMock()
    duties = {"Zurvan": "2026-01-01", "Alexander": "2026-02-01"}

    ed.write_duties_to_bq(bq_client, duties)

    args, kwargs = bq_client.load_table_from_json.call_args
    rows, table_ref = args
    assert table_ref == ed.TABLE_REF
    assert [r["duty"] for r in rows] == ["Alexander", "Zurvan"]
    assert kwargs["job_config"].write_disposition == "WRITE_TRUNCATE"


def test_run_returns_zero_counts_when_nothing_exists(monkeypatch):
    bq_client = MagicMock()
    monkeypatch.setattr(ed.bigquery, "Client", lambda project: bq_client)
    monkeypatch.setattr(ed, "get_existing_duties", lambda c: {})
    monkeypatch.setattr(ed, "get_bronze_duties", lambda c: set())
    write_mock = MagicMock()
    monkeypatch.setattr(ed, "write_duties_to_bq", write_mock)

    result = ed.run()

    assert result == {"duties_total": 0, "duties_new": 0}
    write_mock.assert_not_called()


@freeze_time("2026-03-15")
def test_run_stamps_new_and_legacy_null_duties_with_today_and_preserves_existing(monkeypatch):
    bq_client = MagicMock()
    monkeypatch.setattr(ed.bigquery, "Client", lambda project: bq_client)
    monkeypatch.setattr(
        ed,
        "get_existing_duties",
        lambda c: {"Alexander": "2026-01-01", "LegacyNoDate": None},
    )
    monkeypatch.setattr(ed, "get_bronze_duties", lambda c: {"Alexander", "NewRaid"})
    write_mock = MagicMock()
    monkeypatch.setattr(ed, "write_duties_to_bq", write_mock)

    result = ed.run()

    written = write_mock.call_args[0][1]
    assert written == {
        "Alexander": "2026-01-01",  # untouched - already had a date
        "LegacyNoDate": "2026-03-15",  # legacy null gets backfilled with today
        "NewRaid": "2026-03-15",  # brand new duty stamped with today
    }
    assert result == {"duties_total": 3, "duties_new": 1}  # NewRaid is the only bronze-only duty
