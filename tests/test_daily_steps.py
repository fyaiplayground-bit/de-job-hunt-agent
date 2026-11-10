"""The daily run as separate steps (decision #45): the same results whether the steps run in one
process, as the Windows task does, or one at a time, as Airflow tasks will."""

from datetime import UTC, datetime

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


# ---------------------------------------------------------------- one step from the command line


def cli_services(greenhouse_jobs, freehire_jobs, report_dir):
    def refresh(conn, summary, folder):  # dbt and S3 are tested on their own
        pass

    def send(conn, summary, today):
        pass

    return steps.Services(
        client=lambda: daily_client(greenhouse_jobs, freehire_jobs),
        llm=lambda: FakeClient(BRIEF),
        refresh=refresh,
        send_backup=send,
        report_dir=report_dir,
        now=lambda: NOON,
        targets=TARGETS,
        sleep=lambda _: None,
    )


def cli(db, services, *argv):
    return steps.run_step(db, steps.parse_args(list(argv)), services)


@pytest.mark.db
def test_the_command_line_runs_a_whole_day_like_airflow(
    db, greenhouse_jobs, freehire_jobs, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("JD_ANALYSIS_ENABLED", "false")
    monkeypatch.setenv("LINKEDIN_PUBLIC_ENABLED", "false")
    services = cli_services(greenhouse_jobs, freehire_jobs, tmp_path)
    assert cli(db, services, "start") == 0
    run_id = capsys.readouterr().out.strip().splitlines()[-1]  # what Airflow passes on
    codes = {
        source: cli(db, services, "fetch", "--run-id", run_id, "--source", source)
        for source in ("greenhouse", "freehire", "linkedin")
    }
    assert codes == {"greenhouse": 0, "freehire": 0, "linkedin": steps.SKIPPED}
    for step in ("gate", "summarize"):
        assert cli(db, services, step, "--run-id", run_id) == 0
    assert cli(db, services, "analyze", "--run-id", run_id) == steps.SKIPPED  # AI is off
    assert cli(db, services, "score", "--run-id", run_id) == steps.SKIPPED
    for step in ("analytics", "backup", "finish"):
        assert cli(db, services, step, "--run-id", run_id) == 0

    status, runner, summary = db.execute(
        "select status, runner, summary from ops.daily_runs where daily_run_id = %s", (run_id,)
    ).fetchone()
    assert (status, runner) == ("partial", "airflow")  # partial: gone-company answered 404
    assert (summary["new_jobs"], summary["new_de_jobs"]) == (4, 4)  # as with run_daily
    assert (tmp_path / "2026-11-01.md").is_file()  # the Airflow report folder, not daily's


@pytest.mark.db
def test_a_failed_step_is_saved_and_named_in_the_report(
    db, greenhouse_jobs, freehire_jobs, tmp_path, monkeypatch
):
    monkeypatch.setenv("JD_ANALYSIS_ENABLED", "false")
    services = cli_services(greenhouse_jobs, freehire_jobs, tmp_path)

    def broken(conn, summary, today):
        raise RuntimeError("S3 unreachable")

    services.send_backup = broken
    ctx = steps.start_run(db, NOON, runner="airflow")
    run_id = str(ctx.daily_run_id)
    for step in ("fetch", "gate", "summarize", "analytics"):
        assert cli(db, services, step, "--run-id", run_id) == 0
    with pytest.raises(RuntimeError):
        cli(db, services, "backup", "--run-id", run_id)
    assert cli(db, services, "finish", "--run-id", run_id) == 1

    status, error = db.execute(
        "select status, error from ops.daily_runs where daily_run_id = %s", (ctx.daily_run_id,)
    ).fetchone()
    assert status == "error"
    assert error == "steps didn't finish: backup: RuntimeError: S3 unreachable"
    assert "S3 unreachable" in (tmp_path / "2026-11-01.md").read_text(encoding="utf-8")


@pytest.mark.db
def test_steps_that_never_ran_are_named(db):
    ctx = steps.start_run(db, NOON)
    assert steps.unfinished_steps(db, ctx, ai_enabled=True) == [
        "fetch: didn't run",
        "gate: didn't run",
        "summarize: didn't run",
        "analyze: didn't run",
        "analytics: didn't run",
        "backup: didn't run",
    ]


@pytest.mark.db
def test_a_failed_fetch_retry_still_keeps_the_first_tries_runs(db, greenhouse_jobs, freehire_jobs):
    """A try that fails after an earlier one worked must not wipe the earlier one's run ids."""
    ctx = steps.start_run(db, NOON)
    client = daily_client(greenhouse_jobs, freehire_jobs)
    steps.fetch(db, ctx, client, source="greenhouse", targets=TARGETS, sleep=lambda _: None)
    steps.record_failure(db, ctx, "fetch:greenhouse", RuntimeError("timeout"), NOON)
    steps.fetch(db, ctx, client, source="greenhouse", targets=TARGETS, sleep=lambda _: None)
    steps.summarize(db, ctx)
    assert steps.assemble(db, ctx).new_jobs == 2


@pytest.mark.db
def test_a_second_run_waits_while_one_is_in_progress(db, tmp_path, capsys):
    services = steps.Services(report_dir=tmp_path, now=lambda: NOON)
    first = steps.start_run(db, datetime.now(UTC))
    assert steps.run_in_progress(db) == first.daily_run_id
    assert cli(db, services, "start") == 1
    assert "still running" in capsys.readouterr().err
    db.execute("update ops.daily_runs set status = 'ok'")
    assert steps.run_in_progress(db) is None


@pytest.mark.db
def test_a_run_that_crashed_hours_ago_no_longer_blocks(db):
    steps.start_run(db, datetime.now(UTC))
    db.execute("update ops.daily_runs set started_at = now() - interval '4 hours'")
    assert steps.run_in_progress(db) is None


@pytest.mark.db
def test_windows_runs_are_marked_windows(db):
    ctx = steps.start_run(db, NOON)
    runner = db.execute(
        "select runner from ops.daily_runs where daily_run_id = %s", (ctx.daily_run_id,)
    ).fetchone()[0]
    assert runner == "windows"
