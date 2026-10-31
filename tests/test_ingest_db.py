"""Integration tests: migrations, idempotent loading, run records and the gate step, against the
separate jobhunt_test database (see conftest.db). Skipped when Postgres is down."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from ingestion.http import make_client
from pipeline.db import migrate
from pipeline.gate_step import gate_pending
from pipeline.ingest import ingest_all, ingest_board
from pipeline.load import load_jobs

pytestmark = pytest.mark.db

DAY_1 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def count(conn, table: str) -> int:
    return conn.execute(f"select count(*) from {table}").fetchone()[0]


def start_run(conn) -> object:
    run_id = uuid4()
    conn.execute(
        "insert into raw.ingest_runs (run_id, source, company, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')",
        (run_id,),
    )
    return run_id


def test_migrate_twice_applies_nothing_the_second_time(db):
    assert migrate(db) == []


def test_loading_the_same_jobs_twice_adds_nothing(db, greenhouse_jobs):
    first = load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)
    second = load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)

    assert (first.versions_new, first.sightings_new) == (2, 2)
    assert (second.versions_new, second.sightings_new) == (0, 0)
    assert count(db, "raw.job_postings") == 2
    assert count(db, "raw.job_sightings") == 2


def test_a_changed_posting_adds_one_version_and_keeps_the_old_one(db, greenhouse_jobs):
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)
    greenhouse_jobs[0]["content"] += "&lt;p&gt;Now hybrid.&lt;/p&gt;"

    counts = load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)

    assert counts.versions_new == 1
    versions = db.execute(
        "select count(*) from raw.job_postings where source_job_id = '1001'"
    ).fetchone()[0]
    assert versions == 2


def test_an_updated_at_only_change_adds_no_version(db, greenhouse_jobs):
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)
    for job in greenhouse_jobs:
        job["updated_at"] = "2026-12-01T00:00:00Z"

    counts = load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)

    assert counts.versions_new == 0


def test_the_next_day_adds_sightings_but_no_versions(db, greenhouse_jobs):
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)

    counts = load_jobs(
        db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1 + timedelta(days=1)
    )

    assert (counts.versions_new, counts.sightings_new) == (0, 2)


def mock_client(routes: dict[str, httpx.Response]) -> httpx.Client:
    """A client that answers by URL path; anything else is a 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(request.url.path, httpx.Response(404))

    return make_client(transport=httpx.MockTransport(handler))


def test_ingest_board_records_a_successful_run(db, greenhouse_jobs):
    client = mock_client(
        {"/v1/boards/example/jobs": httpx.Response(200, json={"jobs": greenhouse_jobs})}
    )

    result = ingest_board(db, client, "greenhouse", "example")

    assert (result.status, result.jobs_seen, result.versions_new) == ("ok", 2, 2)
    row = db.execute(
        "select status, jobs_seen, versions_new, finished_at is not null from raw.ingest_runs"
    ).fetchone()
    assert row == ("ok", 2, 2, True)


def test_one_failing_board_does_not_stop_the_others(db, greenhouse_jobs, lever_postings):
    client = mock_client(
        {
            "/v1/boards/example/jobs": httpx.Response(200, json={"jobs": greenhouse_jobs}),
            "/v0/postings/example": httpx.Response(200, json=lever_postings),
        }
    )
    boards = [("greenhouse", "gone-company"), ("greenhouse", "example"), ("lever", "example")]

    results = ingest_all(db, client, boards, sleep=lambda _: None)

    assert [r.status for r in results] == ["error", "ok", "ok"]
    assert "HTTP 404" in results[0].error
    errors = db.execute("select company, error from raw.ingest_runs where status = 'error'")
    assert [(company, "HTTP 404" in error) for company, error in errors] == [("gone-company", True)]
    assert count(db, "raw.job_postings") == 3


def test_gate_checks_every_new_version_once_and_flags_the_injection(db, greenhouse_jobs):
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, start_run(db), DAY_1)

    first = gate_pending(db)
    second = gate_pending(db)

    assert (first.checked, first.alarmed) == (2, 1)
    assert first.tiers == {"clean": 1, "block": 1}  # the injection is hidden with display:none
    assert second.checked == 0
    alarmed_title, cleaned = db.execute(
        "select p.payload->>'title', r.cleaned_text from gate.results r"
        " join raw.job_postings p using (posting_version_id) where r.alarmed"
    ).fetchone()
    assert alarmed_title == "Senior Analytics Engineer"
    assert "Ignore all previous instructions" not in cleaned
    assert "Model data in dbt." in cleaned
