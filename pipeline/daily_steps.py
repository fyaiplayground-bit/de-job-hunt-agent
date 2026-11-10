"""The daily run as separate steps (decision #45).

    start_run → fetch (one per source, or all at once) → gate → summarize → analyze → score
              → analytics → backup → assemble the summary → finish_run

Each step takes the run's context, does one thing, and saves what it found in
ops.daily_run_steps: its part of the day's summary ("fields") and anything a later step needs
("state", such as the ingest run ids). So a step can run in its own process, as an Airflow task
does, be retried on its own, and the summary can always be put together from what was saved.
`pipeline.daily.run_daily` calls these same functions in order for the Windows scheduled task.
"""

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb

from agents import jd_analysis
from agents.llm import LlmClient
from pipeline import daily
from pipeline.config import LlmSettings
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


@dataclass(frozen=True)
class RunContext:
    daily_run_id: int
    local_date: date
    window_days: int


def start_run(conn: psycopg.Connection, now: datetime) -> RunContext:
    """Open today's run: its date in the report's time zone, and how far searches look back."""
    today = now.astimezone(daily.report_timezone()).date()
    window = daily.search_window_days(conn, today)
    run_id = conn.execute(
        "insert into ops.daily_runs (started_at, local_date, status, window_days)"
        " values (%s, %s, 'running', %s) returning daily_run_id",
        (now, today, window),
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


def _saved(conn: psycopg.Connection, daily_run_id: int) -> list[tuple[str, dict, dict]]:
    return conn.execute(
        "select step, fields, state from ops.daily_run_steps where daily_run_id = %s"
        " order by started_at, step",
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


def _summary_fields(summary: daily.DailySummary, step: str) -> dict[str, Any]:
    values = asdict(summary)
    return {name: values[name] for name in STEP_FIELDS[step]}


def _state(conn: psycopg.Connection, ctx: RunContext, prefix: str) -> list[dict[str, Any]]:
    return [state for step, _, state in _saved(conn, ctx.daily_run_id) if step.startswith(prefix)]


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
        run_id for state in _state(conn, ctx, step) for run_id in state["ingest_run_ids"]
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
        run_id for state in _state(conn, ctx, "fetch:") for run_id in state["ingest_run_ids"]
    ]
    summary = _empty(ctx)
    new_versions = daily.summarize_jobs(conn, summary, run_ids)
    save_step(
        conn, ctx, "summarize", _summary_fields(summary, "summarize"),
        {"new_version_ids": new_versions}, started,
    )


def new_version_ids(conn: psycopg.Connection, ctx: RunContext) -> list[int]:
    states = _state(conn, ctx, "summarize")
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
    for step, step_fields, _ in _saved(conn, ctx.daily_run_id):
        if step.startswith("fetch:"):
            summary.targets += step_fields["targets"]
            continue
        for name, value in step_fields.items():
            if name in PAIR_FIELDS:
                value = [tuple(pair) for pair in value]
            setattr(summary, name, value)
    failed = sum(t["status"] == "error" for t in summary.targets)
    summary.status = "ok" if not failed and summary.jd_status != "error" else "partial"
    return summary


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
