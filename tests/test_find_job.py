"""Tests for pipeline/find_job.py: finding a job FL saw elsewhere, explaining a miss, and logging
the check (decision #34). The live freehire search is replaced by a function."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from agents.jd_analysis import load_scope
from pipeline.find_job import (
    check,
    format_result,
    has_phrase,
    normalize_company,
    scope_reasons,
    search_terms,
    stats,
    title_fits,
)
from pipeline.gate_step import gate_pending
from pipeline.load import load_jobs

SCOPE = replace(load_scope(), min_text_chars=0)  # the fixture postings are short
TERMS = [["data", "engineer"], ["analytics", "engineer"]]
TODAY = datetime.now(UTC).date()


def test_normalize_company_ignores_case_punctuation_and_legal_suffixes():
    assert normalize_company("Voto Consulting, LLC") == "votoconsulting"
    assert normalize_company("voto-consulting") == "votoconsulting"
    assert normalize_company("Sigma Computing") == normalize_company("sigmacomputing")
    assert normalize_company("The Home Depot Inc.") == "homedepot"


def test_title_phrase_matching():
    assert has_phrase("Sr. Data Engineer, Platform", ["data", "engineer"])
    assert not has_phrase("Data Center Electrical Engineer", ["data", "engineer"])
    assert not has_phrase("Big Data Engineering Lead", ["data", "engineer"])  # whole words
    assert title_fits("Senior Analytics Engineer", TERMS)
    assert not title_fits("ETL Developer", TERMS)


def test_search_terms_come_from_the_freehire_config():
    assert search_terms() == TERMS


def test_scope_reasons_explain_why_a_stored_job_was_not_analyzed():
    scope = load_scope()
    assert scope_reasons(scope, "Data Engineer", "clean", False, 5000, TODAY, TODAY) == []
    reasons = scope_reasons(scope, "Staff Data Engineer", "review", True, 300,
                            date(2026, 1, 1), TODAY)
    assert reasons == [
        "title level excluded (staff/lead/manager/...)", "gate triage review",
        "freehire marks it stale", "text only 300 characters (cut-off snippet)",
        "not seen on its board since 2026-01-01",
    ]


# ---------------------------------------------------------------- with the test database


@pytest.fixture
def stored(db, greenhouse_jobs):
    run_id = uuid4()
    db.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')", (run_id,),
    )
    load_jobs(db, "greenhouse", "example-data-co", greenhouse_jobs, run_id, datetime.now(UTC))
    gate_pending(db)
    return db


def _no_freehire_call(company, title):
    raise AssertionError("freehire must not be called when the job is stored")


def _check(db, company, title, freehire=_no_freehire_call, boards=frozenset()):
    return check(db, company, title, freehire=freehire, today=TODAY, scope=SCOPE,
                 terms=TERMS, boards=set(boards))


@pytest.mark.db
def test_a_stored_job_is_found_by_company_name_variants(stored):
    for company in ("Example Data Co", "example-data-co", "EXAMPLE DATA"):
        result = _check(stored, company, "data engineer")
        assert result.found and result.reason == "found"
        assert [m.title for m in result.matches] == ["Data Engineer"]
    match = result.matches[0]
    assert (match.triage, match.briefed, match.not_analyzed_because) == ("clean", False, [])
    assert "in analysis scope, not briefed yet" in format_result("x", "y", result)


@pytest.mark.db
def test_found_jobs_say_why_they_were_not_analyzed(stored):
    result = _check(stored, "Example Data Co", "senior analytics engineer")
    assert result.found
    assert result.matches[0].not_analyzed_because == ["gate triage block"]  # the attack fixture


@pytest.mark.db
@pytest.mark.parametrize(
    ("freehire_answer", "boards", "reason"),
    [
        (([{"title": "ETL Developer", "company": "Acme"}], True), (), "freehire_title"),
        (([{"title": "Data Engineer II", "company": "Acme"}], True), (), "freehire_missed"),
        (([], True), ("acme",), "board_missing"),
        (([], True), (), "not_in_freehire"),
        (([], False), (), "unknown"),  # freehire had more pages: can't be sure
    ],
)
def test_misses_get_the_most_likely_reason(stored, freehire_answer, boards, reason):
    result = _check(stored, "Acme", "data engineer", lambda c, t: freehire_answer, boards)
    assert (result.found, result.reason) == (False, reason)


@pytest.mark.db
def test_a_failed_freehire_check_still_logs_the_question(stored):
    def broken(company, title):
        raise TimeoutError("read timed out")

    result = _check(stored, "Acme", "data engineer", broken)
    assert result.reason == "unknown"
    row = stored.execute(
        "select company_query, title_query, found, reason from ops.coverage_checks"
    ).fetchone()
    assert row == ("Acme", "data engineer", False, "unknown")


@pytest.mark.db
def test_every_check_is_logged_and_stats_give_coverage(stored):
    _check(stored, "Example Data Co", "data engineer")
    _check(stored, "Acme", "data engineer", lambda c, t: ([], True))
    _check(stored, "Globex", "analytics engineer",
           lambda c, t: ([{"title": "Analytics Engineer", "company": "Globex"}], True))
    report = stats(stored)
    assert report.splitlines()[0] == "coverage: 1/3 found (33%)"
    assert "not_in_freehire: 1" in report and "freehire_missed: 1" in report
    logged = stored.execute(
        "select matches, freehire_matches from ops.coverage_checks order by coverage_check_id"
    ).fetchall()
    assert logged[0][0][0]["title"] == "Data Engineer" and logged[0][1] is None
    assert logged[2][1] == [{"title": "Analytics Engineer", "company": "Globex"}]
