"""The daily run as separate steps (decision #45): the same results whether the steps run in one
process, as the Windows task does, or one at a time, as Airflow tasks will."""

import pytest

from agents.llm import FakeClient
from pipeline import daily_steps as steps
from pipeline.daily import DailySummary, render_report, run_daily
from tests.test_daily import BRIEF, LLM, NOON, SCOPE, TARGETS, daily_client


def run_one_at_a_time(db, client, fake=None):
    """Each step with a fresh lookup of the run, as separate Airflow tasks would do."""
    run_id = steps.start_run(db, NOON).daily_run_id
    for source in ("greenhouse", "freehire"):
        steps.fetch(
            db,
            steps.run_context(db, run_id),
            client,
            source=source,
            targets=TARGETS,
            sleep=lambda _: None,
        )
    steps.gate(db, steps.run_context(db, run_id))
    steps.summarize(db, steps.run_context(db, run_id))
    if fake is not None:
        steps.analyze(db, steps.run_context(db, run_id), lambda: fake, LLM, 50, SCOPE)
        steps.score(db, steps.run_context(db, run_id), LLM)
    return steps.assemble(db, steps.run_context(db, run_id))


@pytest.mark.db
def test_steps_one_at_a_time_give_the_same_summary_as_run_daily(db, greenhouse_jobs, freehire_jobs):
    summary = run_one_at_a_time(db, daily_client(greenhouse_jobs, freehire_jobs))
    # The numbers test_run_daily_summarizes_new_jobs_after_dedupe expects from run_daily.
    assert summary.status == "partial"  # gone-company answered 404
    assert summary.local_date == "2026-11-01"
    assert summary.new_versions == 5
    assert summary.new_jobs == 4
    assert summary.new_de_jobs == 4
    assert summary.triage_new == {"block": 1, "clean": 4}
    assert [t["source"] for t in summary.targets] == ["greenhouse", "greenhouse", "freehire"]


@pytest.mark.db
def test_ai_steps_one_at_a_time(db, greenhouse_jobs, freehire_jobs):
    fake = FakeClient(BRIEF)
    summary = run_one_at_a_time(db, daily_client(greenhouse_jobs, freehire_jobs), fake)
    assert (summary.jd_status, summary.jd_in_scope, summary.jd_analyzed) == ("ok", 2, 2)
    assert summary.jd_top_skills == [("Python", 2), ("SQL", 2)]  # pairs survive the round trip
    assert (summary.fit_status, summary.fit_scored) == ("ok", 2)
    report = render_report(summary)
    assert "今天最常要求的必备技能：Python（2）、SQL（2）" in report
    assert "## 今天值得投的" in report


@pytest.mark.db
def test_run_daily_saves_every_step(db, greenhouse_jobs, freehire_jobs):
    fake = FakeClient(BRIEF)
    run_daily(
        db,
        daily_client(greenhouse_jobs, freehire_jobs),
        now=lambda: NOON,
        sleep=lambda _: None,
        targets=TARGETS[:2],
        llm=lambda: fake,
        llm_config=LLM,
        scope=SCOPE,
        analytics=lambda conn, summary, folder: setattr(summary, "analytics_status", "ok"),
        backup=lambda conn, summary, today: setattr(summary, "backup_status", "ok"),
    )
    saved = [
        row[0]
        for row in db.execute(
            "select step from ops.daily_run_steps order by started_at, step"
        ).fetchall()
    ]
    assert saved == [
        "fetch:all",
        "gate",
        "summarize",
        "analyze",
        "score",
        "analytics",
        "backup",
    ]


@pytest.mark.db
def test_a_retried_fetch_keeps_what_its_first_try_stored(db, greenhouse_jobs, freehire_jobs):
    """Airflow retries a failed task. Jobs the first try stored must still count as new."""
    client = daily_client(greenhouse_jobs, freehire_jobs)
    ctx = steps.start_run(db, NOON)
    steps.fetch(db, ctx, client, source="greenhouse", targets=TARGETS, sleep=lambda _: None)
    steps.fetch(db, ctx, client, source="greenhouse", targets=TARGETS, sleep=lambda _: None)
    steps.gate(db, ctx)
    steps.summarize(db, ctx)
    summary = steps.assemble(db, ctx)
    assert summary.new_jobs == 2  # the greenhouse board's two jobs, not zero after the retry
    assert len(summary.targets) == 2  # the retry's own lines replace the first try's


@pytest.mark.db
def test_later_steps_refuse_to_run_before_summarize(db):
    ctx = steps.start_run(db, NOON)
    with pytest.raises(ValueError, match="summarize hasn't run"):
        steps.score(db, ctx, LLM)


@pytest.mark.db
def test_assemble_with_only_some_steps_keeps_defaults(db, greenhouse_jobs, freehire_jobs):
    ctx = steps.start_run(db, NOON)
    steps.fetch(
        db,
        ctx,
        daily_client(greenhouse_jobs, freehire_jobs),
        source="greenhouse",
        targets=TARGETS,
        sleep=lambda _: None,
    )
    summary = steps.assemble(db, ctx)
    assert summary.jd_status == "off" and summary.analytics_status == "off"
    assert isinstance(summary, DailySummary)
