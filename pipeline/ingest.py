"""Fetch every configured job board, load it into the raw layer, then run the safety gate.

Run it with:  uv run python -m pipeline.ingest            (all enabled boards)
              uv run python -m pipeline.ingest --source lever --board metabase

One board failing (site down, board removed) is recorded in raw.ingest_runs and the rest carry on.
"""

import argparse
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg

from ingestion.http import make_client
from ingestion.sources import SOURCES, get_source
from pipeline.config import is_source_enabled, load_settings
from pipeline.db import connect, migrate
from pipeline.gate_step import gate_pending
from pipeline.load import load_jobs

COMPANIES_FILE = Path(__file__).resolve().parent.parent / "config" / "companies.toml"
PAUSE_BETWEEN_BOARDS_SECONDS = 1.0


@dataclass(frozen=True)
class BoardResult:
    source: str
    company: str
    run_id: UUID
    status: str  # "ok" or "error"
    jobs_seen: int = 0
    versions_new: int = 0
    error: str | None = None


def read_boards(path: Path = COMPANIES_FILE) -> list[tuple[str, str]]:
    """(source, board token) pairs from config/companies.toml, for known sources only."""
    with path.open("rb") as f:
        config = tomllib.load(f)
    boards = []
    for source, section in config.items():
        get_source(source)  # unknown source name in the file -> clear error
        boards.extend((source, token) for token in section.get("boards", []))
    return boards


def ingest_board(
    conn: psycopg.Connection,
    client: httpx.Client,
    source: str,
    company: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> BoardResult:
    """Fetch and load one board, recording the run (start, outcome, counts) in raw.ingest_runs."""
    run_id = uuid4()
    conn.execute(
        "insert into raw.ingest_runs (run_id, source, company, started_at, status)"
        " values (%s, %s, %s, %s, 'running')",
        (run_id, source, company, now()),
    )
    try:
        jobs = get_source(source).fetch_jobs(client, company)
        counts = load_jobs(conn, source, company, jobs, run_id, fetched_at=now())
    except Exception as exc:  # any failure is this board's problem only; record it and move on
        error = f"{type(exc).__name__}: {exc}"
        conn.execute(
            "update raw.ingest_runs set finished_at = %s, status = 'error', error = %s"
            " where run_id = %s",
            (now(), error[:2000], run_id),
        )
        return BoardResult(source, company, run_id, "error", error=error)

    conn.execute(
        "update raw.ingest_runs"
        " set finished_at = %s, status = 'ok', jobs_seen = %s, versions_new = %s"
        " where run_id = %s",
        (now(), counts.jobs_seen, counts.versions_new, run_id),
    )
    return BoardResult(source, company, run_id, "ok", counts.jobs_seen, counts.versions_new)


def ingest_all(
    conn: psycopg.Connection,
    client: httpx.Client,
    boards: list[tuple[str, str]],
    sleep: Callable[[float], None] = time.sleep,
) -> list[BoardResult]:
    results = []
    for i, (source, company) in enumerate(boards):
        if i:
            sleep(PAUSE_BETWEEN_BOARDS_SECONDS)  # be polite: one board at a time, with a pause
        results.append(ingest_board(conn, client, source, company))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest job boards into the raw layer.")
    parser.add_argument("--source", choices=sorted(SOURCES), help="only this source")
    parser.add_argument("--board", help="only this board token (use with --source)")
    args = parser.parse_args(argv)

    settings = load_settings()
    boards = [
        (source, token)
        for source, token in read_boards()
        if is_source_enabled(source)
        and (args.source is None or source == args.source)
        and (args.board is None or token == args.board)
    ]
    if args.board and args.source and not boards:
        boards = [(args.source, args.board)]  # allow trying a board that isn't in the file yet

    with connect(settings) as conn, make_client() as client:
        applied = migrate(conn)
        if applied:
            print(f"applied migrations: {', '.join(applied)}")
        results = ingest_all(conn, client, boards)
        gate = gate_pending(conn)

    for r in results:
        detail = f"{r.jobs_seen:4} jobs, {r.versions_new:4} new" if r.status == "ok" else r.error
        print(f"{r.status:5}  {r.source:10}  {r.company:16}  {detail}")
    failed = sum(r.status == "error" for r in results)
    print(
        f"\nboards: {len(results)} ({failed} failed) · new versions: "
        f"{sum(r.versions_new for r in results)} · gate checked: {gate.checked}, "
        f"alarmed: {gate.alarmed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
