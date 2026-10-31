"""Fetch every configured target, load it into the raw layer, then run the safety gate.

A target is a job board (config/companies.toml: Greenhouse, Lever) or a saved search
(config/searches.toml: freehire, LinkedIn). Run it with:

    uv run python -m pipeline.ingest                        all enabled targets
    uv run python -m pipeline.ingest --source freehire --days 7   one source, 7-day backfill
    uv run python -m pipeline.ingest --source lever --target metabase
    uv run python -m pipeline.ingest --gate-only            no fetching; recompute the gate

One target failing (site down, board removed) is recorded in raw.ingest_runs and the rest carry
on. LinkedIn is off unless LINKEDIN_PUBLIC_ENABLED=true, and capped at
LINKEDIN_MAX_REQUESTS_PER_DAY requests per UTC day across all runs.
"""

import argparse
import os
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg

from ingestion.context import FetchContext
from ingestion.http import make_client
from ingestion.sources import SOURCES, get_source
from pipeline.config import is_source_enabled, load_settings
from pipeline.db import connect, migrate
from pipeline.gate_step import gate_pending
from pipeline.load import load_jobs

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
COMPANIES_FILE = CONFIG_DIR / "companies.toml"
SEARCHES_FILE = CONFIG_DIR / "searches.toml"
PAUSE_BETWEEN_TARGETS_SECONDS = 1.0


@dataclass(frozen=True)
class Target:
    source: str
    name: str  # board token, or saved-search name
    options: dict[str, Any] = field(default_factory=dict)  # search parameters (empty for boards)


@dataclass(frozen=True)
class TargetResult:
    source: str
    target: str
    run_id: UUID
    status: str  # "ok" or "error"
    jobs_seen: int = 0
    versions_new: int = 0
    requests_made: int = 0
    note: str | None = None
    error: str | None = None


def read_targets(companies: Path = COMPANIES_FILE, searches: Path = SEARCHES_FILE) -> list[Target]:
    """Boards from companies.toml, then saved searches from searches.toml (known sources only)."""
    targets = []
    with companies.open("rb") as f:
        for source, section in tomllib.load(f).items():
            get_source(source)  # unknown source name in the file -> clear error
            targets.extend(Target(source, token) for token in section.get("boards", []))
    with searches.open("rb") as f:
        for source, entries in tomllib.load(f).items():
            get_source(source)
            for entry in entries:
                options = {k: v for k, v in entry.items() if k != "name"}
                targets.append(Target(source, entry["name"], options))
    return targets


def _request_budget(conn: psycopg.Connection, source: str, today: datetime) -> int | None:
    """Requests this run may still make today, for sources with a daily cap; None = no cap."""
    module = get_source(source)
    cap_variable = getattr(module, "DAILY_CAP_VARIABLE", None)
    if cap_variable is None:
        return None
    cap = int(os.environ.get(cap_variable, module.DEFAULT_DAILY_CAP))
    used = conn.execute(
        "select coalesce(sum(requests_made), 0) from raw.ingest_runs"
        " where source = %s and (started_at at time zone 'UTC')::date = %s",
        (source, today.date()),
    ).fetchone()[0]
    return max(cap - used, 0)


def _known_job_ids(conn: psycopg.Connection, source: str) -> frozenset[str]:
    rows = conn.execute(
        "select distinct source_job_id from raw.job_postings where source = %s", (source,)
    )
    return frozenset(row[0] for row in rows)


def ingest_target(
    conn: psycopg.Connection,
    client: httpx.Client,
    target: Target,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> TargetResult:
    """Fetch and load one target; record the run (outcome, counts, requests) in raw.ingest_runs."""
    run_id = uuid4()
    started = now()
    conn.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, %s, %s, %s, 'running')",
        (run_id, target.source, target.name, started),
    )
    module = get_source(target.source)
    ctx = FetchContext(
        client=client,
        options=target.options,
        request_budget=_request_budget(conn, target.source, started),
        known_job_ids=_known_job_ids(conn, target.source)
        if hasattr(module, "DAILY_CAP_VARIABLE")
        else frozenset(),
        sleep=sleep,
    )
    try:
        jobs = module.fetch_jobs(ctx, target.name)
        counts = load_jobs(
            conn, target.source, target.name, jobs, run_id, now(), seen_only=ctx.seen_only
        )
    except Exception as exc:  # any failure is this target's problem only; record it, move on
        error = f"{type(exc).__name__}: {exc}"
        conn.execute(
            "update raw.ingest_runs"
            " set finished_at = %s, status = 'error', error = %s, requests_made = %s"
            " where run_id = %s",
            (now(), error[:2000], ctx.requests_made, run_id),
        )
        return TargetResult(
            target.source,
            target.name,
            run_id,
            "error",
            requests_made=ctx.requests_made,
            error=error,
        )

    note = "request budget used up; the rest waits for tomorrow" if ctx.budget_exhausted else None
    conn.execute(
        "update raw.ingest_runs"
        " set finished_at = %s, status = 'ok', jobs_seen = %s, versions_new = %s,"
        "  requests_made = %s, note = %s"
        " where run_id = %s",
        (now(), counts.jobs_seen, counts.versions_new, ctx.requests_made, note, run_id),
    )
    return TargetResult(
        target.source,
        target.name,
        run_id,
        "ok",
        counts.jobs_seen,
        counts.versions_new,
        ctx.requests_made,
        note,
    )


def ingest_all(
    conn: psycopg.Connection,
    client: httpx.Client,
    targets: list[Target],
    sleep: Callable[[float], None] = time.sleep,
) -> list[TargetResult]:
    results = []
    for i, target in enumerate(targets):
        if i:
            sleep(PAUSE_BETWEEN_TARGETS_SECONDS)  # be polite: one target at a time, with a pause
        results.append(ingest_target(conn, client, target, sleep=sleep))
    return results


def select_targets(
    targets: list[Target],
    source: str | None = None,
    name: str | None = None,
    days: int | None = None,
) -> list[Target]:
    """Enabled targets matching the filters; `days` overrides posted_within_days for searches."""
    chosen = []
    for t in targets:
        if not is_source_enabled(t.source):
            continue
        if (source and t.source != source) or (name and t.name != name):
            continue
        if days is not None and "posted_within_days" in t.options:
            t = Target(t.source, t.name, {**t.options, "posted_within_days": days})
        chosen.append(t)
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest job boards and searches into raw.")
    parser.add_argument("--source", choices=sorted(SOURCES), help="only this source")
    parser.add_argument(
        "--target", "--board", dest="target", help="only this board token or search name"
    )
    parser.add_argument("--days", type=int, help="searches: posted within N days (backfill)")
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help="don't fetch; only run the gate on postings not yet checked by the current rules "
        "(use after a rules change to recompute from raw)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    targets = (
        []
        if args.gate_only
        else select_targets(read_targets(), args.source, args.target, args.days)
    )
    if not args.gate_only and args.source and args.target and not targets:
        if args.source in ("greenhouse", "lever"):  # try a board that isn't in the file yet
            targets = [Target(args.source, args.target)]

    with connect(settings) as conn, make_client() as client:
        applied = migrate(conn)
        if applied:
            print(f"applied migrations: {', '.join(applied)}")
        results = ingest_all(conn, client, targets)
        gate = gate_pending(conn)

    for r in results:
        if r.status == "ok":
            detail = f"{r.jobs_seen:5} jobs, {r.versions_new:5} new, {r.requests_made:3} requests"
            detail += f"  ({r.note})" if r.note else ""
        else:
            detail = r.error
        print(f"{r.status:5}  {r.source:10}  {r.target:20}  {detail}")
    failed = sum(r.status == "error" for r in results)
    print(
        f"\ntargets: {len(results)} ({failed} failed) · new versions: "
        f"{sum(r.versions_new for r in results)} · gate checked: {gate.checked}, "
        f"alarmed: {gate.alarmed}"
    )
    if gate.checked:
        print("triage: " + ", ".join(f"{tier} {n}" for tier, n in sorted(gate.tiers.items())))
    if gate.tiers.get("review") or gate.tiers.get("block"):
        print("postings need a look: uv run python -m pipeline.alarm_report")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
