"""The daily run as separate steps (decisions #45, #46).

    start_run → fetch (one per source, or all at once) → gate → summarize → analyze → score
              → analytics → backup → assemble the summary → finish_run

Each step takes the run's context, does one thing, and saves what it found in
ops.daily_run_steps: its part of the day's summary ("fields") and anything a later step needs
("state", such as the ingest run ids). So a step can run in its own process, as an Airflow task
does, be retried on its own, and the summary can always be put together from what was saved.
`pipeline.daily.run_daily` calls these same functions in order for the Windows scheduled task;
the Airflow DAG (dags/daily_job_hunt.py) calls them one per task through the command line:

    python -m pipeline.daily_steps start --runner airflow     # prints the new run's id
    python -m pipeline.daily_steps fetch --run-id 12 --source greenhouse
    python -m pipeline.daily_steps gate --run-id 12            # ... and so on, then:
    python -m pipeline.daily_steps finish --run-id 12

Exit codes: 0 done, 99 skipped (Airflow shows the task as skipped), 1 failed.
"""

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from agents import jd_analysis
from agents.llm import AnthropicClient, LlmClient
from ingestion.http import make_client
from pipeline import daily
from pipeline.config import (
    LlmSettings,
    daily_analysis_settings,
    is_source_enabled,
    llm_settings,
    load_settings,
)
from pipeline.db import connect, migrate
from pipeline.gate_step import gate_pending
from pipeline.ingest import ingest_all, read_targets, select_targets

STEP_ORDER = ("fetch", "gate", "summarize", "analyze", "score", "analytics", "backup")
# Which summary fields each step fills in.
STEP_FIELDS = {
    "summarize": (
        "new_versions", "new_jobs", "new_de_jobs", "top_de_companies", "new_de_titles",
        "triage_new", "flagged_unlabeled",
    ),
    "analyze": tuple(f.name for f in fields(daily.DailySummary) if f.name.startswith("jd_")),
    "score": tuple(f.name for f in fields(daily.DailySummary) if f.name.startswith("fit_")),
    "analytics": ("analytics_status", "analytics_error", "coverage"),
    "backup": ("backup_status", "backup", "backup_error"),
}
# Fields holding (name, count) pairs: JSON turns tuples into lists, so they are turned back.
PAIR_FIELDS = ("top_de_companies", "new_de_titles", "jd_top_skills")
# A run still marked running after this long crashed without finishing; it no longer blocks.
RUN_TIMEOUT_HOURS = 3
# While Airflow runs beside the Windows task (step 4.4), its reports go here, so they never
# replace the day's Windows report (which the logon catch-up also reads).
AIRFLOW_REPORT_DIR = daily.REPORT_DIR / "airflow"
SKIPPED = 99  # BashOperator's default skip_on_exit_code


@dataclass(frozen=True)
class RunContext:
    daily_run_id: int
    local_date: date
    window_days: int


def run_in_progress(conn: psycopg.Connection) -> int | None:
    """The id of a run started in the last few hours that hasn't finished, if any."""
    row = conn.execute(
        "select daily_run_id from ops.daily_runs where status = 'running'"
        " and started_at > now() - make_interval(hours => %s) order by daily_run_id desc limit 1",
        (RUN_TIMEOUT_HOURS,),
    ).fetchone()
    return row[0] if row else None


def start_run(conn: psycopg.Connection, now: datetime, runner: str = "windows") -> RunContext:
    """Open today's run: its date in the report's time zone, and how far searches look back."""
    today = now.astimezone(daily.report_timezone()).date()
    window = daily.search_window_days(conn, today)
    run_id = conn.execute(
        "insert into ops.daily_runs (started_at, local_date, status, window_days, runner)"
        " values (%s, %s, 'running', %s, %s) returning daily_run_id",
        (now, today, window, runner),
    ).fetchone()[0]
    return RunContext(run_id, today, window)


def run_context(conn: psycopg.Connection, daily_run_id: int) -> RunContext:
    row = conn.execute(
        "select local_date, window_days from ops.daily_runs where daily_run_id = %s",
        (daily_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"no daily run {daily_run_id}")
    return RunContext(daily_run_id, row[0], row[1])


def _saved(conn: psycopg.Connection, daily_run_id: int) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "select step, status, fields, state, error from ops.daily_run_steps"
            " where daily_run_id = %s order by started_at, step",
            (daily_run_id,),
        ).fetchall()


def save_step(
    conn: psycopg.Connection,
    ctx: RunContext,
    step: str,
    step_fields: dict[str, Any],
    state: dict[str, Any],
    started: datetime,
) -> None:
    conn.execute(
        "insert into ops.daily_run_steps"
        " (daily_run_id, step, status, fields, state, started_at, finished_at)"
        " values (%s, %s, 'ok', %s, %s, %s, %s)"
        " on conflict (daily_run_id, step) do update set status = excluded.status,"
        " fields = excluded.fields, state = excluded.state, error = null,"
        " started_at = excluded.started_at, finished_at = excluded.finished_at",
        (ctx.daily_run_id, step, Jsonb(step_fields), Jsonb(state), started, datetime.now(UTC)),
    )


def record_failure(
    conn: psycopg.Connection, ctx: RunContext, step: str, exc: BaseException, started: datetime
) -> None:
    """Mark a step failed. What an earlier try saved (such as its ingest run ids) is kept."""
    conn.execute(
        "insert into ops.daily_run_steps"
        " (daily_run_id, step, status, fields, state, error, started_at, finished_at)"
        " values (%s, %s, 'error', '{}', '{}', %s, %s, %s)"
        " on conflict (daily_run_id, step) do update set status = 'error',"
        " error = excluded.error, finished_at = excluded.finished_at",
        (ctx.daily_run_id, step, f"{type(exc).__name__}: {exc}", started, datetime.now(UTC)),
    )


def _summary_fields(summary: daily.DailySummary, step: str) -> dict[str, Any]:
    values = asdict(summary)
    return {name: values[name] for name in STEP_FIELDS[step]}


def _state(conn: psycopg.Connection, ctx: RunContext, prefix: str) -> list[dict[str, Any]]:
    rows = _saved(conn, ctx.daily_run_id)
    return [row["state"] for row in rows if row["step"].startswith(prefix)]


def _empty(ctx: RunContext) -> daily.DailySummary:
    return daily.DailySummary(local_date=ctx.local_date.isoformat(), window_days=ctx.window_days)


# ---------------------------------------------------------------- the steps


def fetch(
    conn: psycopg.Connection,
    ctx: RunContext,
    client: httpx.Client,
    source: str | None = None,
    targets: list | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Fetch every enabled target, or one source's. A retried fetch keeps the ingest run ids of
    earlier tries, so jobs an interrupted try already stored still count as new today."""
    started = datetime.now(UTC)
    chosen = select_targets(
        targets if targets is not None else read_targets(), source=source, days=ctx.window_days
    )
    results = ingest_all(conn, client, chosen, sleep=sleep)
    step = f"fetch:{source or 'all'}"
    earlier = [
        run_id for state in _state(conn, ctx, step) for run_id in state.get("ingest_run_ids", [])
    ]
    run_ids = list(dict.fromkeys([*earlier, *(str(r.run_id) for r in results)]))
    save_step(
        conn, ctx, step, {"targets": daily.summarize_targets(results)},
        {"ingest_run_ids": run_ids}, started,
    )


def gate(conn: psycopg.Connection, ctx: RunContext) -> None:
    started = datetime.now(UTC)
    counts = gate_pending(conn)
    save_step(conn, ctx, "gate", {}, {"checked": counts.checked}, started)


def summarize(conn: psycopg.Connection, ctx: RunContext) -> None:
    """Which jobs are new today: every copy first stored by today's fetches."""
    started = datetime.now(UTC)
    run_ids = [
        run_id
        for state in _state(conn, ctx, "fetch:")
        for run_id in state.get("ingest_run_ids", [])
    ]
    summary = _empty(ctx)
    new_versions = daily.summarize_jobs(conn, summary, run_ids)
    save_step(
        conn, ctx, "summarize", _summary_fields(summary, "summarize"),
        {"new_version_ids": new_versions}, started,
    )


def new_version_ids(conn: psycopg.Connection, ctx: RunContext) -> list[int]:
    states = [
        row["state"]
        for row in _saved(conn, ctx.daily_run_id)
        if row["step"] == "summarize" and row["status"] == "ok"
    ]
    if not states:
        raise ValueError("summarize hasn't run for this daily run")
    return states[0]["new_version_ids"]


def analyze(
    conn: psycopg.Connection,
    ctx: RunContext,
    llm: Callable[[], LlmClient],
    settings: LlmSettings,
    daily_max: int,
    scope: jd_analysis.Scope | None = None,
) -> str:
    """Brief today's new in-scope jobs. Returns the step's status: ok, partial or error."""
    started = datetime.now(UTC)
    summary = _empty(ctx)
    daily.analyze_new(
        conn, summary, new_version_ids(conn, ctx), llm, settings, daily_max, scope
    )
    save_step(conn, ctx, "analyze", _summary_fields(summary, "analyze"), {}, started)
    return summary.jd_status


def score(
    conn: psycopg.Connection,
    ctx: RunContext,
    settings: LlmSettings,
    profile_folder: Path | None = None,
) -> None:
    started = datetime.now(UTC)
    summary = _empty(ctx)
    daily.score_new(
        conn, summary, new_version_ids(conn, ctx), settings, profile_folder, ctx.local_date
    )
    save_step(conn, ctx, "score", _summary_fields(summary, "score"), {}, started)


def analytics(
    conn: psycopg.Connection,
    ctx: RunContext,
    refresh: Callable[[psycopg.Connection, daily.DailySummary, Path | None], None],
    profile_folder: Path | None = None,
) -> None:
    started = datetime.now(UTC)
    summary = _empty(ctx)
    refresh(conn, summary, profile_folder)
    save_step(conn, ctx, "analytics", _summary_fields(summary, "analytics"), {}, started)


def backup(
    conn: psycopg.Connection,
    ctx: RunContext,
    send: Callable[[psycopg.Connection, daily.DailySummary, date], None],
) -> None:
    started = datetime.now(UTC)
    summary = _empty(ctx)
    send(conn, summary, ctx.local_date)
    save_step(conn, ctx, "backup", _summary_fields(summary, "backup"), {}, started)


# ---------------------------------------------------------------- putting it together


def assemble(conn: psycopg.Connection, ctx: RunContext) -> daily.DailySummary:
    """The day's summary from the saved steps. Steps that didn't run leave their defaults."""
    summary = _empty(ctx)
    for row in _saved(conn, ctx.daily_run_id):
        if row["status"] != "ok":
            continue
        if row["step"].startswith("fetch:"):
            summary.targets += row["fields"]["targets"]
            continue
        for name, value in row["fields"].items():
            if name in PAIR_FIELDS:
                value = [tuple(pair) for pair in value]
            setattr(summary, name, value)
    failed = sum(t["status"] == "error" for t in summary.targets)
    summary.status = "ok" if not failed and summary.jd_status != "error" else "partial"
    return summary


def unfinished_steps(conn: psycopg.Connection, ctx: RunContext, ai_enabled: bool) -> list[str]:
    """Steps that failed or never ran, with the error when there is one. Empty = a whole run.

    The Windows path runs every step in one go, so this matters when the steps run as separate
    tasks: a task that failed leaves its step missing here, and the report must say so.
    Scoring is expected only when the briefing step went well enough to score."""
    rows = _saved(conn, ctx.daily_run_id)
    ok = {row["step"]: row for row in rows if row["status"] == "ok"}
    problems = [f"{row['step']}: {row['error']}" for row in rows if row["status"] == "error"]
    failed = {row["step"] for row in rows if row["status"] == "error"}
    needed = ["gate", "summarize"]
    if ai_enabled:
        needed.append("analyze")
        if ok.get("analyze", {}).get("fields", {}).get("jd_status") in ("ok", "partial"):
            needed.append("score")
    needed += ["analytics", "backup"]
    if not any(step.startswith("fetch:") for step in ok) and not any(
        step.startswith("fetch:") for step in failed
    ):
        problems.insert(0, "fetch: didn't run")
    problems += [f"{step}: didn't run" for step in needed if step not in ok and step not in failed]
    return problems


def finish_run(
    conn: psycopg.Connection, ctx: RunContext, summary: daily.DailySummary, report_path: Path
) -> None:
    conn.execute(
        "update ops.daily_runs set finished_at = %s, status = %s, window_days = %s,"
        " summary = %s, report_path = %s, error = %s where daily_run_id = %s",
        (
            datetime.now(UTC), summary.status, summary.window_days, Jsonb(asdict(summary)),
            str(report_path), summary.error, ctx.daily_run_id,
        ),
    )


# ---------------------------------------------------------------- one step from the command line


@dataclass
class Services:
    """What the steps reach outside the database. Tests swap in fakes."""

    client: Callable[[], httpx.Client] = make_client
    llm: Callable[[], LlmClient] = AnthropicClient
    refresh: Callable[..., None] = daily.refresh_analytics
    send_backup: Callable[..., None] = daily.backup_database
    report_dir: Path = AIRFLOW_REPORT_DIR
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    targets: list | None = None  # None = config/companies.toml and searches.toml
    sleep: Callable[[float], None] = time.sleep


def run_step(conn: psycopg.Connection, args: argparse.Namespace, services: Services) -> int:
    """Run one step for the command line. A failure is saved on the step, then raised."""
    if args.step == "start":
        migrate(conn)
        running = run_in_progress(conn)
        if running is not None:
            print(f"daily run {running} is still running; not starting another", file=sys.stderr)
            return 1
        ctx = start_run(conn, services.now(), runner=args.runner)
        print(ctx.daily_run_id)  # the last line: Airflow hands it to the later tasks
        return 0

    ctx = run_context(conn, args.run_id)
    if args.step == "finish":
        return _finish(conn, ctx, services)
    step = f"fetch:{args.source or 'all'}" if args.step == "fetch" else args.step
    started = datetime.now(UTC)
    try:
        return _one_step(conn, ctx, args, services)
    except Exception as exc:
        record_failure(conn, ctx, step, exc, started)
        raise


def _one_step(
    conn: psycopg.Connection, ctx: RunContext, args: argparse.Namespace, services: Services
) -> int:
    if args.step == "fetch":
        if args.source and not is_source_enabled(args.source):
            print(f"{args.source} is turned off in .env; skipped")
            return SKIPPED
        with services.client() as client:
            fetch(
                conn, ctx, client, source=args.source, targets=services.targets,
                sleep=services.sleep,
            )
    elif args.step == "gate":
        gate(conn, ctx)
    elif args.step == "summarize":
        summarize(conn, ctx)
    elif args.step == "analyze":
        analysis = daily_analysis_settings()
        if not analysis.enabled:
            print("JD analysis is turned off in .env; skipped")
            return SKIPPED
        status = analyze(conn, ctx, services.llm, llm_settings(), analysis.daily_max)
        print(f"briefing: {status}")
    elif args.step == "score":
        briefed = [
            row for row in _saved(conn, ctx.daily_run_id)
            if row["step"] == "analyze" and row["status"] == "ok"
        ]
        if not briefed or briefed[0]["fields"]["jd_status"] not in ("ok", "partial"):
            print("no briefing to score today; skipped")
            return SKIPPED
        score(conn, ctx, llm_settings())
    elif args.step == "analytics":
        analytics(conn, ctx, services.refresh)
    elif args.step == "backup":
        backup(conn, ctx, services.send_backup)
    return 0


def _finish(conn: psycopg.Connection, ctx: RunContext, services: Services) -> int:
    summary = assemble(conn, ctx)
    problems = unfinished_steps(conn, ctx, daily_analysis_settings().enabled)
    if problems:
        summary.status = "error"
        summary.error = "steps didn't finish: " + "; ".join(problems)
    report = daily.render_report(summary)
    path = daily.write_report(report, summary.local_date, services.report_dir)
    finish_run(conn, ctx, summary, path)
    print(report.splitlines()[2])
    print(f"report: {path}")
    return 1 if summary.status == "error" else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m pipeline.daily_steps")
    steps = parser.add_subparsers(dest="step", required=True)
    start = steps.add_parser("start", help="open a run and print its id")
    start.add_argument("--runner", choices=("airflow", "windows"), default="airflow")
    for name in (*STEP_ORDER, "finish"):
        step = steps.add_parser(name)
        step.add_argument("--run-id", type=int, required=True)
        if name == "fetch":
            step.add_argument("--source", help="one source (default: every enabled one)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    with connect(load_settings()) as conn:
        return run_step(conn, args, Services())


if __name__ == "__main__":
    sys.exit(main())
