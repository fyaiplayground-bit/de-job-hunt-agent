"""Tests for agents/jd_analysis.py: which postings get analyzed, what the LLM is asked for, and
how briefs are stored (decision #31). FakeClient stands in for the API; nothing is paid for."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from agents.jd_analysis import (
    BRIEF_SCHEMA,
    Candidate,
    _display_fields,
    load_scope,
    run,
    select_candidates,
)
from agents.llm import FakeClient
from pipeline.config import LlmSettings
from pipeline.daily import DE_TITLE
from pipeline.gate_step import gate_pending
from pipeline.load import load_jobs

SETTINGS = LlmSettings(model="claude-opus-5-5", effort="medium")
BRIEF = {
    "archetype": "pipeline_de",
    "seniority": "mid",
    "years_required": 3,
    "must_haves": [
        {"skill": "Python", "exact_phrases": ["Python"], "weight": "core"},
        {"skill": "Apache Airflow", "exact_phrases": ["Airflow"], "weight": "normal"},
    ],
    "nice_to_haves": [{"skill": "dbt", "exact_phrases": ["dbt"]}],
    "work_mode": "remote",
    "locations": ["Remote - US"],
    "remote_regions": ["US"],
    "salary": {"min": None, "max": None, "currency": None},
    "sponsorship": "unstated",
    "hidden_signals": [],
    "knockout_questions_likely": ["Are you authorized to work in the US?"],
    "safety_flags": [],
}


# ---------------------------------------------------------------- no database


def test_scope_title_rule_matches_the_daily_report():
    """Same postings count as "DE" in the report and in analysis (Postgres \\M = Python \\b)."""
    assert load_scope().title_include.replace(r"\M", r"\b") == DE_TITLE.pattern


def _assert_strict(schema: dict, path: str = "brief") -> None:
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False, path
        assert set(schema["required"]) == set(schema["properties"]), path
        for name, sub in schema["properties"].items():
            _assert_strict(sub, f"{path}.{name}")
    if schema.get("type") == "array":
        _assert_strict(schema["items"], f"{path}[]")


def test_brief_schema_requires_every_field_and_allows_no_extras():
    _assert_strict(BRIEF_SCHEMA)


def test_display_fields_per_source():
    assert _display_fields("greenhouse", "acme", {
        "company_name": "Acme Inc", "location": {"name": "Denver, CO"},
        "absolute_url": "https://example.com/1",
    }) == ("Acme Inc", "Denver, CO", "https://example.com/1")
    assert _display_fields("lever", "acme", {
        "categories": {"location": "Austin, TX"}, "workplaceType": "hybrid",
        "hostedUrl": "https://example.com/2",
    }) == ("acme", "Austin, TX (hybrid)", "https://example.com/2")
    assert _display_fields("lever", "acme", {
        "categories": {"location": "Remote (US)"}, "workplaceType": "remote", "hostedUrl": "",
    })[1] == "Remote (US)"
    assert _display_fields("freehire", "acme", {
        "company": "Acme Inc", "location": "New York", "work_mode": "onsite",
        "url": "https://example.com/3",
    }) == ("Acme Inc", "New York (onsite)", "https://example.com/3")


def test_candidate_data_puts_board_facts_before_the_text():
    candidate = Candidate(1, "greenhouse", "Acme", "Data Engineer", "", "", "Build pipelines.")
    assert candidate.data() == (
        "Company: Acme\nTitle: Data Engineer\nLocation on the job board: not given\n\n"
        "Build pipelines."
    )


# ---------------------------------------------------------------- with the test database


def _start_run(conn) -> object:
    run_id = uuid4()
    conn.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')",
        (run_id,),
    )
    return run_id


def _job(template: dict, job_id: int, title: str) -> dict:
    job = copy.deepcopy(template)
    job["id"] = job_id
    job["internal_job_id"] = job_id
    job["title"] = title
    job["absolute_url"] = f"https://example.com/careers/{job_id}"
    return job


@pytest.fixture
def loaded(db, greenhouse_jobs):
    """The fixture's clean DE posting and its hidden-text attack posting (gate: block), plus a
    clean Analytics Engineer, a Staff DE and a designer; all seen today and gated."""
    jobs = greenhouse_jobs + [
        _job(greenhouse_jobs[0], 2000, "Analytics Engineer"),
        _job(greenhouse_jobs[0], 2001, "Staff Data Engineer"),
        _job(greenhouse_jobs[0], 2002, "Product Designer"),
    ]
    load_jobs(db, "greenhouse", "example", jobs, _start_run(db), datetime.now(UTC))
    gate_pending(db)
    return db


def _titles(conn, scope=None) -> set[str]:
    todo, _ = select_candidates(conn, scope or load_scope(), "jd-analysis@2", SETTINGS.model)
    return {c.title for c in todo}


@pytest.mark.db
def test_selects_open_de_postings_that_passed_the_gate(loaded):
    assert _titles(loaded) == {"Data Engineer", "Analytics Engineer"}


@pytest.mark.db
def test_postings_in_review_or_block_never_reach_the_llm(loaded):
    triage = dict(loaded.execute(
        "select p.payload->>'title', g.triage from gate.results g"
        " join raw.job_postings p using (posting_version_id)"
    ).fetchall())
    assert triage["Senior Analytics Engineer"] == "block"  # the hidden-text attack fixture
    assert "Senior Analytics Engineer" not in _titles(loaded)

    loaded.execute(
        "update gate.results set triage = 'review' where posting_version_id = (select"
        " posting_version_id from raw.job_postings where payload->>'title' = 'Data Engineer')"
    )
    assert _titles(loaded) == {"Analytics Engineer"}


@pytest.mark.db
def test_postings_not_seen_lately_are_skipped(db, greenhouse_jobs):
    old = datetime.now(UTC) - timedelta(days=10)
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, _start_run(db), old)
    gate_pending(db)
    assert _titles(db) == set()
    assert _titles(db, replace(load_scope(), open_within_days=30)) == {"Data Engineer"}


@pytest.mark.db
def test_stale_freehire_postings_are_skipped(db, freehire_jobs):
    load_jobs(db, "freehire", "us-data-engineering", freehire_jobs, _start_run(db),
              datetime.now(UTC))
    gate_pending(db)
    with_stale = _titles(db, replace(load_scope(), skip_freehire_stale=False))
    without_stale = _titles(db)
    assert len(with_stale) == len(without_stale) + 1


@pytest.mark.db
def test_run_stores_briefs_with_board_facts_and_skips_them_next_time(loaded):
    client = FakeClient(BRIEF)
    summary = run(loaded, client, SETTINGS)
    assert (summary.in_scope, summary.selected, summary.analyzed) == (2, 2, 2)
    assert summary.cost_usd == pytest.approx(0.016)  # 2 fake calls at 1000 in / 200 out

    rows = loaded.execute(
        "select prompt_version, model, scope_version, brief from agents.jd_briefs"
        " order by brief->>'title'"
    ).fetchall()
    assert [r[:3] for r in rows] == [("jd-analysis@2", "claude-opus-5-5", 1)] * 2
    brief = next(r[3] for r in rows if r[3]["title"] == "Data Engineer")
    assert (brief["title"], brief["company"], brief["source"]) == (
        "Data Engineer", "Example Data Co", "greenhouse",
    )
    assert brief["url"].startswith("https://example.com/careers/")
    assert brief["must_haves"] == BRIEF["must_haves"]
    # what the model was given: the cleaned text as data, never the raw HTML
    assert client.requests[0].user.startswith("<data>\nCompany: ")
    assert "&lt;p&gt;" not in client.requests[0].user

    again = run(loaded, client, SETTINGS)
    assert (again.in_scope, again.already_done, again.selected) == (2, 2, 0)
    assert len(client.requests) == 2


@pytest.mark.db
def test_dry_run_estimates_without_calling(loaded):
    client = FakeClient(BRIEF)
    summary = run(loaded, client, SETTINGS, dry_run=True)
    assert summary.selected == 2 and summary.estimated_usd > 0
    assert client.requests == []
    assert loaded.execute("select count(*) from agents.jd_briefs").fetchone()[0] == 0


@pytest.mark.db
def test_limit_and_failures(loaded):
    summary = run(loaded, FakeClient(BRIEF, stop_reason="refusal"), SETTINGS, limit=1)
    assert summary.selected == 1 and summary.analyzed == 0
    assert len(summary.failed) == 1 and "declined" in summary.failed[0][1]
    assert loaded.execute("select count(*) from agents.jd_briefs").fetchone()[0] == 0
