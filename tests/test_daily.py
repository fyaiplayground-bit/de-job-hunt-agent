"""The daily run: search window, summary, report, lock, and what happens when Postgres is down."""

from dataclasses import replace
from datetime import UTC, date, datetime

import httpx
import psycopg
import pytest

from agents.jd_analysis import load_scope
from agents.llm import FakeClient
from ingestion.http import make_client
from pipeline.config import (
    ConfigError,
    DailyAnalysisSettings,
    LlmSettings,
    Settings,
    daily_analysis_settings,
)
from pipeline.daily import (
    DailySummary,
    acquire_lock,
    render_report,
    run_daily,
    search_window_days,
    wait_for_database,
    write_report,
)
from pipeline.ingest import Target

TODAY = date(2026, 11, 1)
NOON = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)  # 11:00 in Los Angeles


def record_run(conn, local_date: date, status: str = "ok") -> None:
    conn.execute(
        "insert into ops.daily_runs (started_at, local_date, status) values (now(), %s, %s)",
        (local_date, status),
    )


@pytest.mark.db
@pytest.mark.parametrize(
    ("last_runs", "expected"),
    [
        ([], 2),  # first run ever
        ([date(2026, 10, 31)], 2),  # ran yesterday: 1 day + 1 overlap
        ([date(2026, 10, 28)], 5),  # laptop off for a few days: catch up
        ([date(2026, 9, 1)], 7),  # capped
        ([date(2026, 10, 28), date(2026, 10, 31)], 2),  # the latest run counts
    ],
)
def test_search_window_grows_with_the_gap_since_the_last_good_run(db, last_runs, expected):
    for day in last_runs:
        record_run(db, day)
    record_run(db, date(2026, 10, 31), status="error")  # failed runs don't count

    if not last_runs:
        db.execute("delete from ops.daily_runs")
    assert search_window_days(db, TODAY) == expected


def daily_client(greenhouse_jobs, freehire_jobs) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/boards/example/jobs":
            return httpx.Response(200, json={"jobs": greenhouse_jobs})
        if request.url.path.startswith("/api/v1/agent/jobs/search"):
            return httpx.Response(200, json={"data": freehire_jobs})
        return httpx.Response(404)

    return make_client(transport=httpx.MockTransport(handler))


TARGETS = [
    Target("greenhouse", "example"),
    Target("freehire", "us-de", {"query": "title:data engineer", "posted_within_days": 2}),
    Target("greenhouse", "gone-company"),
]


@pytest.mark.db
def test_run_daily_summarizes_new_jobs_after_dedupe(db, greenhouse_jobs, freehire_jobs):
    client = daily_client(greenhouse_jobs, freehire_jobs)

    summary = run_daily(db, client, now=lambda: NOON, sleep=lambda _: None, targets=TARGETS)

    assert summary.status == "partial"  # gone-company answered 404
    assert summary.local_date == "2026-11-01"
    assert summary.new_versions == 5
    assert summary.new_jobs == 4  # greenhouse 1001 also came through freehire
    assert summary.new_de_jobs == 4
    assert summary.flagged_unlabeled == 1  # the hidden injection in greenhouse 1002
    assert summary.triage_new == {"block": 1, "clean": 4}


@pytest.mark.db
def test_a_second_run_the_same_day_finds_nothing_new(db, greenhouse_jobs, freehire_jobs):
    client = daily_client(greenhouse_jobs, freehire_jobs)
    run_daily(db, client, now=lambda: NOON, sleep=lambda _: None, targets=TARGETS[:2])

    later = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
    second = run_daily(db, client, now=lambda: later, sleep=lambda _: None, targets=TARGETS[:2])

    assert (second.status, second.new_versions, second.new_jobs) == ("ok", 0, 0)


@pytest.mark.db
def test_only_one_daily_run_at_a_time(db):
    other = psycopg.connect(db.info.dsn + f" password={db.info.password}", autocommit=True)
    try:
        assert acquire_lock(db) is True
        assert acquire_lock(other) is False
    finally:
        other.close()


def test_report_is_deterministic_and_leads_with_one_line():
    summary = DailySummary(
        local_date="2026-11-01",
        window_days=2,
        status="ok",
        new_versions=312,
        new_jobs=300,
        new_de_jobs=41,
        top_de_companies=[("example-data-co", 3)],
        new_de_titles=[("example-data-co", "Data Engineer")],
        triage_new={"clean": 310, "benign": 2},
    )

    first, second = render_report(summary), render_report(summary)

    assert first == second
    assert first.splitlines()[2] == (
        "✅ **0 个来源，新增 300 个职位（DE 类 41 个），没有需要你看的报警。**"
    )
    assert "- example-data-co — Data Engineer" in first


def test_reports_are_dated_and_latest_is_overwritten(tmp_path):
    write_report("first\n", "2026-10-31", tmp_path)
    write_report("second\n", "2026-11-01", tmp_path)

    assert (tmp_path / "2026-10-31.md").read_text(encoding="utf-8") == "first\n"
    assert (tmp_path / "latest.md").read_text(encoding="utf-8") == "second\n"


def test_database_down_starts_docker_once_then_gives_up():
    unreachable = Settings("127.0.0.1", 1, "nope", "nobody", "x")
    started = []

    def refuse(_settings):
        raise psycopg.OperationalError("connection refused")

    conn = wait_for_database(
        unreachable,
        lambda: started.append(1),
        wait_seconds=0,
        sleep=lambda _: None,
        connect_to=refuse,
    )

    assert conn is None
    assert started == [1]
    report = render_report(
        replace(DailySummary("2026-11-01", 0, "error"), error="Is Docker Desktop paused?")
    )
    assert report.splitlines()[2].startswith("❌")
    assert "Docker Desktop paused" in report


# ---------------------------------------------------------------- the AI step (decision #33)

SCOPE = replace(load_scope(), min_text_chars=0)  # the fixture postings are short
LLM = LlmSettings(model="claude-opus-5-5", effort="medium")
BRIEF = {
    "archetype": "pipeline_de", "seniority": "mid", "years_required": 3,
    "must_haves": [{"skill": "Python", "exact_phrases": ["Python"], "weight": "core"},
                   {"skill": "SQL", "exact_phrases": ["SQL"], "weight": "core"}],
    "nice_to_haves": [], "work_mode": "remote", "locations": [], "remote_regions": [],
    "salary": {"min": None, "max": None, "currency": None}, "sponsorship": "unstated",
    "hidden_signals": [], "knockout_questions_likely": [], "safety_flags": [],
}


def _daily(db, client, llm, **kwargs):
    return run_daily(
        db, client, now=lambda: NOON, sleep=lambda _: None, targets=TARGETS[:2],
        llm=llm, llm_config=LLM, scope=SCOPE, **kwargs,
    )


@pytest.mark.db
def test_daily_run_briefs_todays_new_in_scope_jobs(db, greenhouse_jobs, freehire_jobs):
    fake = FakeClient(BRIEF)
    summary = _daily(db, daily_client(greenhouse_jobs, freehire_jobs), lambda: fake)

    assert summary.status == "ok"
    assert summary.jd_status == "ok"
    # 4 new jobs: the hidden-text attack is blocked by the gate, one freehire posting is stale
    assert (summary.jd_in_scope, summary.jd_analyzed) == (2, 2)
    assert len(fake.requests) == 2
    assert summary.jd_cost_usd == pytest.approx(0.016)
    assert summary.jd_top_skills == [("Python", 2), ("SQL", 2)]
    assert db.execute("select count(*) from agents.jd_briefs").fetchone()[0] == 2
    report = render_report(summary)
    assert "范围内的新职位 2 个，拆解了 2 个（0 个来自缓存），花费 $0.02" in report
    assert "今天最常要求的必备技能：Python（2）、SQL（2）" in report

    later = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
    second = run_daily(
        db, daily_client(greenhouse_jobs, freehire_jobs), now=lambda: later,
        sleep=lambda _: None, targets=TARGETS[:2], llm=lambda: fake, llm_config=LLM, scope=SCOPE,
    )
    assert (second.jd_in_scope, second.jd_analyzed, len(fake.requests)) == (0, 0, 2)


@pytest.mark.db
def test_daily_cap_limits_the_ai_step(db, greenhouse_jobs, freehire_jobs):
    fake = FakeClient(BRIEF)
    summary = _daily(db, daily_client(greenhouse_jobs, freehire_jobs), lambda: fake, daily_max=1)
    assert (summary.jd_analyzed, summary.jd_skipped_by_limit) == (1, 1)
    assert "因为每日上限没拆：1 个" in render_report(summary)


@pytest.mark.db
def test_a_changed_old_job_is_not_briefed(db, greenhouse_jobs, freehire_jobs):
    """Only new jobs: an edited posting of a job seen before must not sneak in a backfill."""
    _daily(db, daily_client(greenhouse_jobs, freehire_jobs), None)
    greenhouse_jobs[0]["content"] += "&lt;p&gt;Now with Kafka.&lt;/p&gt;"
    fake = FakeClient(BRIEF)
    summary = _daily(db, daily_client(greenhouse_jobs, freehire_jobs), lambda: fake)
    assert (summary.new_versions, summary.new_jobs) == (1, 0)
    assert (summary.jd_in_scope, len(fake.requests)) == (0, 0)


@pytest.mark.db
def test_ai_failure_keeps_the_days_ingest(db, greenhouse_jobs, freehire_jobs):
    def broken():
        raise RuntimeError("no API key")

    summary = _daily(db, daily_client(greenhouse_jobs, freehire_jobs), broken)
    assert summary.status == "partial"
    assert (summary.jd_status, summary.jd_error) == ("error", "RuntimeError: no API key")
    assert summary.new_jobs == 4
    assert db.execute("select count(*) from raw.job_postings").fetchone()[0] == 5
    assert "这一步出错了，抓取和闸门的结果不受影响" in render_report(summary)


@pytest.mark.db
def test_one_failed_posting_is_reported_and_the_rest_continue(db, greenhouse_jobs, freehire_jobs):
    fake = FakeClient(BRIEF, stop_reason="refusal")
    summary = _daily(db, daily_client(greenhouse_jobs, freehire_jobs), lambda: fake)
    assert (summary.status, summary.jd_status) == ("ok", "partial")
    assert len(summary.jd_failed) == 2 and "declined" in summary.jd_failed[0]


@pytest.mark.db
def test_ai_step_off_without_a_client(db, greenhouse_jobs, freehire_jobs):
    summary = _daily(db, daily_client(greenhouse_jobs, freehire_jobs), None)
    assert summary.jd_status == "off"
    assert "已关闭" in render_report(summary)


def test_daily_analysis_settings(monkeypatch):
    monkeypatch.delenv("JD_ANALYSIS_ENABLED", raising=False)
    monkeypatch.delenv("JD_ANALYSIS_DAILY_MAX", raising=False)
    assert daily_analysis_settings(env_file=None) == DailyAnalysisSettings(True, 50)
    monkeypatch.setenv("JD_ANALYSIS_ENABLED", "false")
    monkeypatch.setenv("JD_ANALYSIS_DAILY_MAX", "10")
    assert daily_analysis_settings(env_file=None) == DailyAnalysisSettings(False, 10)
    monkeypatch.setenv("JD_ANALYSIS_DAILY_MAX", "lots")
    with pytest.raises(ConfigError, match="JD_ANALYSIS_DAILY_MAX"):
        daily_analysis_settings(env_file=None)
