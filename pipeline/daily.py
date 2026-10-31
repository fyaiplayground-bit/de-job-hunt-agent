"""The daily run: check the database, fetch every enabled source, run the gate, write a report.

    uv run python -m pipeline.daily

`run_daily()` is a plain function: the Windows scheduled task calls it through `main()` today, and
an Airflow task (or a cloud scheduler) can call the same function later (decision #27).

- Search window: searches look back (days since the last successful daily run + 1), between 2
  and 7 days, so a laptop that was off for a few days catches up instead of missing jobs.
- One run at a time: a Postgres advisory lock; a second run started meanwhile just exits.
- Report: output/daily/<date>.md plus output/daily/latest.md (gitignored, stays on this machine).
"""

import os
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg
from psycopg.types.json import Jsonb

from ingestion.http import make_client
from pipeline.config import Settings, load_settings
from pipeline.db import connect, migrate
from pipeline.gate_step import gate_pending
from pipeline.ingest import TargetResult, ingest_all, read_targets, select_targets
from pipeline.safety_gate import GATE_VERSION

REPORT_DIR = Path(__file__).resolve().parent.parent / "output" / "daily"
LOCK_KEY = 2026_1101  # any constant; every daily run takes the same advisory lock
MIN_WINDOW_DAYS, MAX_WINDOW_DAYS = 2, 7
DOCKER_WAIT_SECONDS = 180
# Rough title filter for the report only. The real DE filter belongs in dbt staging (M3).
DE_TITLE = re.compile(
    r"data engineer|analytics engineer|data platform|etl\b|data infrastructure|data pipeline", re.I
)


def report_timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("REPORT_TIMEZONE", "America/Los_Angeles"))


@dataclass
class DailySummary:
    local_date: str
    window_days: int
    status: str = "running"  # ok / partial / error
    targets: list[dict[str, Any]] = field(default_factory=list)
    new_versions: int = 0
    new_jobs: int = 0
    new_de_jobs: int = 0
    top_de_companies: list[tuple[str, int]] = field(default_factory=list)
    new_de_titles: list[tuple[str, str]] = field(default_factory=list)  # (company, title)
    triage_new: dict[str, int] = field(default_factory=dict)
    flagged_unlabeled: int = 0  # review/block under the current rules with no label yet
    error: str | None = None


def search_window_days(conn: psycopg.Connection, today: date) -> int:
    """Days since the last ok/partial daily run, plus 1 for overlap, kept within 2..7."""
    last = conn.execute(
        "select max(local_date) from ops.daily_runs where status in ('ok', 'partial')"
    ).fetchone()[0]
    if last is None:
        return MIN_WINDOW_DAYS
    return max(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, (today - last).days + 1))


def _summarize(
    conn: psycopg.Connection, summary: DailySummary, results: list[TargetResult]
) -> None:
    """New = everything this run's ingest runs added: a job is new when every copy of it (across
    sources) was first stored by one of these runs. Run ids, not clocks, so it can't drift."""
    run_ids = [r.run_id for r in results]
    summary.targets = [
        {
            "source": r.source,
            "target": r.target,
            "status": r.status,
            "jobs_seen": r.jobs_seen,
            "versions_new": r.versions_new,
            "requests_made": r.requests_made,
            "note": r.note,
            "error": r.error,
        }
        for r in results
    ]
    summary.new_versions = sum(r.versions_new for r in results)
    new_jobs = conn.execute(
        "with first_seen as ("
        "  select i.identity_key from dedupe.job_identity i"
        "  join raw.job_postings p using (posting_version_id)"
        "  group by i.identity_key having bool_and(p.run_id = any(%s)))"
        " select p.company, coalesce(p.payload->>'title', p.payload->>'text', '')"
        " from dedupe.jobs j join first_seen using (identity_key)"
        " join raw.job_postings p on p.posting_version_id = j.chosen_posting_version_id"
        " order by p.company, 2",
        (run_ids,),
    ).fetchall()
    de_jobs = [(company, title) for company, title in new_jobs if DE_TITLE.search(title)]
    summary.new_jobs = len(new_jobs)
    summary.new_de_jobs = len(de_jobs)
    summary.top_de_companies = Counter(c for c, _ in de_jobs).most_common(10)
    summary.new_de_titles = de_jobs[:30]
    summary.triage_new = dict(
        conn.execute(
            "select r.triage, count(*) from gate.results r"
            " join raw.job_postings p using (posting_version_id)"
            " where r.gate_version = %s and p.run_id = any(%s) group by 1 order by 1",
            (GATE_VERSION, run_ids),
        ).fetchall()
    )
    summary.flagged_unlabeled = conn.execute(
        "select count(*) from gate.results r where r.gate_version = %s"
        " and r.triage in ('review', 'block')"
        " and not exists (select 1 from gate.labels l"
        "                 where l.posting_version_id = r.posting_version_id)",
        (GATE_VERSION,),
    ).fetchone()[0]


def run_daily(
    conn: psycopg.Connection,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    targets: list | None = None,
) -> DailySummary:
    """Fetch, gate and summarize. The caller holds the lock and records the run."""
    started = now()
    today = started.astimezone(report_timezone()).date()
    window = search_window_days(conn, today)
    summary = DailySummary(local_date=today.isoformat(), window_days=window)
    chosen = select_targets(targets if targets is not None else read_targets(), days=window)
    results = ingest_all(conn, client, chosen, sleep=sleep)
    gate_pending(conn)
    _summarize(conn, summary, results)
    failed = sum(r.status == "error" for r in results)
    summary.status = "ok" if not failed else "partial"
    return summary


def render_report(s: DailySummary) -> str:
    """The report as Markdown. Same summary in, same text out."""
    failed = [t for t in s.targets if t["status"] == "error"]
    icon = {"ok": "✅", "partial": "⚠️", "error": "❌"}.get(s.status, "…")
    look = f"{s.flagged_unlabeled} 个需要你看" if s.flagged_unlabeled else "没有需要你看的报警"
    lines = [
        f"# 每日运行 {s.local_date}",
        "",
        f"{icon} **{len(s.targets)} 个来源"
        + (f"（{len(failed)} 个失败）" if failed else "")
        + f"，新增 {s.new_jobs} 个职位（DE 类 {s.new_de_jobs} 个），{look}。**",
        "",
        f"搜索回看 {s.window_days} 天 · 新版本 {s.new_versions} 条",
    ]
    if s.error:
        lines += ["", "## 出错了", "", f"```\n{s.error}\n```"]
    if s.top_de_companies:
        lines += ["", "## 今天新增的 DE 类职位（按公司）", ""]
        lines += [f"- {company}: {n}" for company, n in s.top_de_companies]
    if s.new_de_titles:
        lines += ["", "## 职位", ""]
        lines += [f"- {company} — {title}" for company, title in s.new_de_titles]
        if s.new_de_jobs > len(s.new_de_titles):
            lines.append(f"- …另外 {s.new_de_jobs - len(s.new_de_titles)} 个")
    if s.triage_new:
        lines += ["", "## 安全闸门（今天新进来的）", ""]
        lines += [f"- {tier}: {n}" for tier, n in sorted(s.triage_new.items())]
    if s.flagged_unlabeled:
        lines += ["", "需要看的报警：让 Claude 跑 `uv run python -m pipeline.alarm_report`"]
    if s.targets:
        lines += ["", "## 各来源", "", "| 状态 | 来源 | 目标 | 看到 | 新增 | 请求 | 备注 |"]
        lines.append("| --- | --- | --- | ---: | ---: | ---: | --- |")
        for t in s.targets:
            note = t["error"] or t["note"] or ""
            lines.append(
                f"| {t['status']} | {t['source']} | {t['target']} | {t['jobs_seen']} "
                f"| {t['versions_new']} | {t['requests_made']} | {note[:80]} |"
            )
    return "\n".join(lines) + "\n"


def write_report(text: str, local_date: str, directory: Path = REPORT_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{local_date}.md"
    path.write_text(text, encoding="utf-8")
    (directory / "latest.md").write_text(text, encoding="utf-8")
    return path


def wait_for_database(
    settings: Settings,
    start_docker: Callable[[], None],
    wait_seconds: int = DOCKER_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    connect_to: Callable[[Settings], psycopg.Connection] = connect,
) -> psycopg.Connection | None:
    """Connect; if Postgres isn't up, start Docker Desktop once and keep trying for a while."""
    started_docker = False
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return connect_to(settings)
        except psycopg.OperationalError:
            if not started_docker:
                start_docker()
                started_docker = True
            if time.monotonic() >= deadline:
                return None
            sleep(10)


def start_docker_desktop() -> None:
    """Open Docker Desktop (per-user install). The compose service restarts with it."""
    exe = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "DockerDesktop"
        / "Docker Desktop.exe"
    )
    if exe.exists():
        subprocess.Popen([str(exe)], close_fds=True)  # noqa: S603 - fixed local path


def acquire_lock(conn: psycopg.Connection) -> bool:
    """Take the daily-run lock for this connection's lifetime; False if another run holds it."""
    return conn.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]


def main() -> int:
    # The scheduled task writes to a log file, where Windows would default to a non-UTF-8 code page.
    sys.stdout.reconfigure(encoding="utf-8")
    settings = load_settings()
    now = datetime.now(UTC)
    local_date = now.astimezone(report_timezone()).date().isoformat()

    conn = wait_for_database(settings, start_docker_desktop)
    if conn is None:
        summary = DailySummary(local_date=local_date, window_days=0, status="error")
        summary.error = (
            "Postgres didn't answer within 3 minutes, even after starting Docker Desktop. "
            "Is Docker Desktop paused? Open it and click Resume, then run the daily again."
        )
        path = write_report(render_report(summary), local_date)
        print(f"error: database not reachable; report: {path}")
        return 1

    with conn:
        migrate(conn)
        if not acquire_lock(conn):
            print("another daily run is in progress; nothing to do")
            return 0
        run_id = conn.execute(
            "insert into ops.daily_runs (started_at, local_date, status)"
            " values (%s, %s, 'running') returning daily_run_id",
            (now, local_date),
        ).fetchone()[0]
        try:
            with make_client() as client:
                summary = run_daily(conn, client, now=lambda: datetime.now(UTC))
        except Exception as exc:  # record any crash, write the report, exit non-zero
            summary = DailySummary(local_date=local_date, window_days=0, status="error")
            summary.error = f"{type(exc).__name__}: {exc}"
        path = write_report(render_report(summary), summary.local_date)
        conn.execute(
            "update ops.daily_runs set finished_at = %s, status = %s, window_days = %s,"
            " summary = %s, report_path = %s, error = %s where daily_run_id = %s",
            (
                datetime.now(UTC),
                summary.status,
                summary.window_days,
                Jsonb(asdict(summary)),
                str(path),
                summary.error,
                run_id,
            ),
        )
    print(render_report(summary).splitlines()[2])
    print(f"report: {path}")
    return 0 if summary.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
