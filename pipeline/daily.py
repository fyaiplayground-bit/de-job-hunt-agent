"""The daily run: check the database, fetch every enabled source, run the gate, write a report.

    uv run python -m pipeline.daily

`run_daily()` is a plain function: the Windows scheduled task calls it through `main()`. It runs
the steps in pipeline/daily_steps.py one after another; an Airflow DAG calls the same steps as
separate tasks (decisions #27, #45).

- Search window: searches look back (days since the last successful daily run + 1), between 2
  and 7 days, so a laptop that was off for a few days catches up instead of missing jobs.
- One run at a time: a Postgres advisory lock; a second run started meanwhile just exits.
- AI step (decision #33): that day's new jobs in the analysis scope get a jd-analysis brief, up
  to JD_ANALYSIS_DAILY_MAX. If the AI step fails, the fetched and gated data still count.
- Report: output/daily/<date>.md plus output/daily/latest.md (gitignored, stays on this machine).
"""

import argparse
import os
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg

from agents import fit_scoring, jd_analysis
from agents.coverage_report import coverage_lines
from agents.llm import AnthropicClient, LlmClient
from agents.profile import load_profile
from ingestion.http import make_client
from pipeline.config import (
    LlmSettings,
    Settings,
    daily_analysis_settings,
    llm_settings,
    load_settings,
    profile_dir,
)
from pipeline.db import connect, migrate
from pipeline.ingest import TargetResult
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
    # AI step: jd-analysis on today's new jobs
    jd_status: str = "off"  # off / ok / partial (some postings failed) / error (step failed)
    jd_in_scope: int = 0  # today's new jobs inside config/analysis_scope.toml
    jd_analyzed: int = 0
    jd_from_cache: int = 0
    jd_cost_usd: float = 0.0
    jd_skipped_by_limit: int = 0
    jd_failed: list[str] = field(default_factory=list)
    jd_top_skills: list[tuple[str, int]] = field(default_factory=list)
    jd_error: str | None = None
    # Fit scoring of today's briefs against the profile in PROFILE_DIR (decision #35)
    fit_status: str = "off"  # off / ok / error
    fit_profile: str = ""  # whose profile scored them
    fit_scored: int = 0
    fit_worth: list[dict[str, Any]] = field(default_factory=list)  # apply / apply_referral
    fit_skipped: dict[str, int] = field(default_factory=dict)  # reason -> count
    fit_error: str | None = None
    # dbt and the coverage report (decision #41)
    analytics_status: str = "off"  # off / ok / error
    analytics_error: str | None = None
    # S3 backup (decision #44)
    backup_status: str = "off"  # off / ok / warning / error
    backup: dict[str, Any] = field(default_factory=dict)
    backup_error: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)


def search_window_days(conn: psycopg.Connection, today: date) -> int:
    """Days since the last ok/partial daily run, plus 1 for overlap, kept within 2..7."""
    last = conn.execute(
        "select max(local_date) from ops.daily_runs where status in ('ok', 'partial')"
    ).fetchone()[0]
    if last is None:
        return MIN_WINDOW_DAYS
    return max(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, (today - last).days + 1))


def summarize_targets(results: list[TargetResult]) -> list[dict[str, Any]]:
    """One line per fetched target for the report."""
    return [
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


def summarize_jobs(
    conn: psycopg.Connection, summary: DailySummary, run_ids: list[Any]
) -> list[int]:
    """New = everything these ingest runs added: a job is new when every copy of it (across
    sources) was first stored by one of these runs. Run ids, not clocks, so it can't drift.
    Returns the chosen posting version of each new job."""
    run_ids = [str(run_id) for run_id in run_ids]
    summary.new_versions = conn.execute(
        "select count(*) from raw.job_postings where run_id = any(%s::uuid[])", (run_ids,)
    ).fetchone()[0]
    new_jobs = conn.execute(
        "with first_seen as ("
        "  select i.identity_key from dedupe.job_identity i"
        "  join raw.job_postings p using (posting_version_id)"
        "  group by i.identity_key having bool_and(p.run_id = any(%s::uuid[])))"
        " select p.company, coalesce(p.payload->>'title', p.payload->>'text', ''),"
        " p.posting_version_id"
        " from dedupe.jobs j join first_seen using (identity_key)"
        " join raw.job_postings p on p.posting_version_id = j.chosen_posting_version_id"
        " order by p.company, 2",
        (run_ids,),
    ).fetchall()
    de_jobs = [(company, title) for company, title, _ in new_jobs if DE_TITLE.search(title)]
    summary.new_jobs = len(new_jobs)
    summary.new_de_jobs = len(de_jobs)
    summary.top_de_companies = Counter(c for c, _ in de_jobs).most_common(10)
    summary.new_de_titles = de_jobs[:30]
    summary.triage_new = dict(
        conn.execute(
            "select r.triage, count(*) from gate.results r"
            " join raw.job_postings p using (posting_version_id)"
            " where r.gate_version = %s and p.run_id = any(%s::uuid[]) group by 1 order by 1",
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
    return [posting_version_id for _, _, posting_version_id in new_jobs]


def analyze_new(
    conn: psycopg.Connection,
    summary: DailySummary,
    new_versions: list[int],
    llm: Callable[[], LlmClient],
    settings: LlmSettings,
    daily_max: int,
    scope: jd_analysis.Scope | None,
) -> None:
    """Brief today's new in-scope jobs. Any failure of the whole step is recorded, not raised:
    the AI step must never cost the day's fetched and gated data."""
    try:
        result = jd_analysis.run(
            conn, llm(), settings, limit=daily_max, scope=scope, only=new_versions
        )
    except Exception as exc:  # e.g. no API key, API down: report it and keep the day's ingest
        summary.jd_status = "error"
        summary.jd_error = f"{type(exc).__name__}: {exc}"
        return
    summary.jd_status = "partial" if result.failed else "ok"
    summary.jd_in_scope = result.in_scope
    summary.jd_analyzed = result.analyzed
    summary.jd_from_cache = result.from_cache
    summary.jd_cost_usd = round(result.cost_usd, 4)
    summary.jd_skipped_by_limit = result.skipped_by_limit
    summary.jd_failed = [f"{pvid}: {error}" for pvid, error in result.failed]
    # most asked first, ties by name, so the same briefs always give the same report
    ranked = sorted(result.must_have_counts.items(), key=lambda item: (-item[1], item[0]))
    summary.jd_top_skills = ranked[:5]


def score_new(
    conn: psycopg.Connection,
    summary: DailySummary,
    new_versions: list[int],
    settings: LlmSettings,
    profile_folder: Path | None,
    today: date,
) -> None:
    """Score today's briefs (code only, free). A failure is reported, never raised."""
    try:
        profile = load_profile(profile_folder or profile_dir())
        rules = fit_scoring.load_rules()
        result = fit_scoring.run(
            conn, profile=profile, rules=rules, only=new_versions, today=today,
            brief_model=settings.model,
        )
    except Exception as exc:  # e.g. a broken profile file: keep the rest of the day's work
        summary.fit_status = "error"
        summary.fit_error = f"{type(exc).__name__}: {exc}"
        return
    name = profile.applicant["contact"]["name"]
    summary.fit_profile = f"{name}（样本档案）" if profile.bank.sample else name
    summary.fit_status = "ok"
    summary.fit_scored = result.scored
    worth, skipped = [], Counter()
    for _, brief, r in result.results:
        if r["decision"] == "skip":
            skipped[fit_scoring.skip_reason(r, rules)] += 1
            continue
        worth.append({
            "company": brief["company"], "title": brief["title"], "url": brief["url"],
            "score": r["score"], "decision": r["decision"],
            "must": round(100 * (r["must_have_coverage"] or 0)),
            "work_mode": r["work_mode"], "location": r["location"],
        })
    summary.fit_worth = sorted(worth, key=lambda w: (-w["score"], w["company"], w["title"]))
    summary.fit_skipped = dict(sorted(skipped.items(), key=lambda item: (-item[1], item[0])))


def refresh_analytics(
    conn: psycopg.Connection, summary: DailySummary, profile_folder: Path | None
) -> None:
    """Rebuild the dbt models and read the coverage report. A failure is reported, never raised:
    the day's ingest doesn't depend on it, and the models can be rebuilt at any time."""
    from agents.coverage_report import read_coverage
    from pipeline.analytics import refresh

    try:
        result = refresh(conn, profile_folder)
        if result.ok:
            summary.coverage = read_coverage(conn)
    except Exception as exc:  # e.g. a broken profile file: keep the rest of the day's work
        summary.analytics_status = "error"
        summary.analytics_error = f"{type(exc).__name__}: {exc}"
        return
    summary.analytics_status = "ok" if result.ok else "error"
    if not result.ok:
        summary.analytics_error = "; ".join(result.failed) or result.error


def backup_database(conn: psycopg.Connection, summary: DailySummary, today: date) -> None:
    """Send today's backup to S3 when it is set up. A failure is reported, never raised."""
    from pipeline.backup import backup_settings, run_backup

    settings = backup_settings()
    if not settings.enabled:
        return
    try:
        result = run_backup(conn, today, settings)
    except Exception as exc:  # no network, an expired key: the day's work is still done
        summary.backup_status = "error"
        summary.backup_error = f"{type(exc).__name__}: {exc}"
        return
    summary.backup = result.as_dict()
    summary.backup_status = "warning" if result.warnings or result.restore_problems else "ok"


def _backup_lines(s: DailySummary) -> list[str]:
    if s.backup_status == "error":
        return [f"❌ 备份失败，其他结果不受影响：`{s.backup_error}`"]
    b = s.backup
    lines = [f"- 已传到 S3：`{b['key']}`（{b['size_mb']} MB）"]
    if b["monthly_key"]:
        lines.append(f"- 本月第一份，另存为 `{b['monthly_key']}`")
    if b["restore_problems"] == []:
        lines.append("- 恢复检查：恢复成功，各表行数一致")
    for problem in b["restore_problems"] or []:
        lines.append(f"- ⚠️ 恢复检查：{problem}")
    lines += [f"- ⚠️ {warning}" for warning in b["warnings"]]
    return lines


def run_daily(
    conn: psycopg.Connection,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    targets: list | None = None,
    llm: Callable[[], LlmClient] | None = None,
    llm_config: LlmSettings | None = None,
    daily_max: int = 50,
    scope: jd_analysis.Scope | None = None,
    profile_folder: Path | None = None,
    analytics: Callable[[psycopg.Connection, DailySummary, Path | None], None] | None = None,
    backup: Callable[[psycopg.Connection, DailySummary, date], None] | None = None,
    run_id: int | None = None,
) -> DailySummary:
    """Fetch, gate, brief and score today's new jobs (when `llm` is given) and summarize, one
    step after another (pipeline/daily_steps.py, decision #45). The caller holds the lock and
    records the run; without a `run_id` a run is opened here."""
    from pipeline import daily_steps as steps

    ctx = steps.run_context(conn, run_id) if run_id else steps.start_run(conn, now())
    steps.fetch(conn, ctx, client, targets=targets, sleep=sleep)
    steps.gate(conn, ctx)
    steps.summarize(conn, ctx)
    if llm is not None:
        settings = llm_config or llm_settings()
        if steps.analyze(conn, ctx, llm, settings, daily_max, scope) in ("ok", "partial"):
            steps.score(conn, ctx, settings, profile_folder)
    if analytics is not None:
        steps.analytics(conn, ctx, analytics, profile_folder)
    if backup is not None:
        steps.backup(conn, ctx, backup)
    return steps.assemble(conn, ctx)


def _analysis_lines(s: DailySummary) -> list[str]:
    if s.jd_status == "off":
        return ["已关闭（`.env` 里 JD_ANALYSIS_ENABLED=false）。"]
    if s.jd_status == "error":
        return [f"❌ 这一步出错了，抓取和闸门的结果不受影响：`{s.jd_error}`"]
    lines = [
        f"- 范围内的新职位 {s.jd_in_scope} 个，拆解了 {s.jd_analyzed} 个"
        f"（{s.jd_from_cache} 个来自缓存），花费 ${s.jd_cost_usd:.2f}"
    ]
    if s.jd_skipped_by_limit:
        lines.append(f"- 因为每日上限没拆：{s.jd_skipped_by_limit} 个")
    if s.jd_failed:
        lines.append(f"- ⚠️ 失败 {len(s.jd_failed)} 个：")
        lines += [f"  - {failure[:160]}" for failure in s.jd_failed]
    if s.jd_top_skills:
        top = "、".join(f"{skill}（{n}）" for skill, n in s.jd_top_skills)
        lines.append(f"- 今天最常要求的必备技能：{top}")
    return lines


FIT_LABEL = {"apply_referral": "投 + 找内推", "apply": "投"}
FIT_SHOWN = 15


def _fit_lines(s: DailySummary) -> list[str]:
    if s.fit_status == "error":
        return [f"❌ 打分出错了，其他结果不受影响：`{s.fit_error}`"]
    if not s.fit_scored:
        return ["今天没有新的简报可以打分。"]
    lines = [
        f"- {FIT_LABEL[w['decision']]} · {w['score']} 分 · [{w['company']} — {w['title']}]"
        f"({w['url']}) · 必备 {w['must']}% · {w['work_mode']} · {w['location']}"
        for w in s.fit_worth[:FIT_SHOWN]
    ]
    if len(s.fit_worth) > FIT_SHOWN:
        lines.append(f"- …另外 {len(s.fit_worth) - FIT_SHOWN} 个值得投")
    if not s.fit_worth:
        lines.append(f"- 今天打分的 {s.fit_scored} 个职位都不建议投")
    if s.fit_skipped:
        reasons = "、".join(f"{reason} {n}" for reason, n in s.fit_skipped.items())
        lines.append(f"- 跳过 {sum(s.fit_skipped.values())} 个：{reasons}")
    return lines


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
    lines += ["", "## AI 拆解（今天的新职位）", ""] + _analysis_lines(s)
    if s.fit_status != "off":
        lines += ["", f"## 今天值得投的（按 {s.fit_profile or '档案'} 打分）", ""]
        lines += _fit_lines(s)
    if s.analytics_status != "off":
        lines += ["", f"## 技能覆盖（按 {s.fit_profile or '当前档案'} 算）", ""]
        if s.analytics_status == "error":
            lines.append(f"❌ 这一步出错了，其他结果不受影响：`{s.analytics_error}`")
        else:
            lines += coverage_lines(s.coverage)
    if s.backup_status != "off":
        lines += ["", "## 备份", ""] + _backup_lines(s)
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


def already_ran_today(local_date: str, directory: Path = REPORT_DIR) -> bool:
    """Today's report exists and isn't a failed run. Reads a file, not the database, so a login
    after today's run doesn't start Docker just to find out."""
    path = directory / f"{local_date}.md"
    if not path.is_file():
        return False
    return not any(
        line.startswith("❌ **") for line in path.read_text(encoding="utf-8").splitlines()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.daily")
    parser.add_argument(
        "--if-not-run-today", action="store_true",
        help="do nothing if today's run already succeeded (the scheduled task uses this)",
    )
    args = parser.parse_args(argv)
    # The scheduled task writes to a log file, where Windows would default to a non-UTF-8 code page.
    sys.stdout.reconfigure(encoding="utf-8")
    now = datetime.now(UTC)
    local_date = now.astimezone(report_timezone()).date().isoformat()
    if args.if_not_run_today and already_ran_today(local_date):
        print(f"{local_date}: already ran today; nothing to do")
        return 0
    settings = load_settings()

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
        from pipeline import daily_steps as steps

        ctx = steps.start_run(conn, now)
        analysis = daily_analysis_settings()
        try:
            with make_client() as client:
                summary = run_daily(
                    conn, client, now=lambda: datetime.now(UTC),
                    llm=AnthropicClient if analysis.enabled else None,
                    daily_max=analysis.daily_max,
                    analytics=refresh_analytics,
                    backup=backup_database,
                    run_id=ctx.daily_run_id,
                )
        except Exception as exc:  # record any crash, write the report, exit non-zero
            summary = DailySummary(local_date=local_date, window_days=0, status="error")
            summary.error = f"{type(exc).__name__}: {exc}"
        path = write_report(render_report(summary), summary.local_date)
        steps.finish_run(conn, ctx, summary, path)
    print(render_report(summary).splitlines()[2])
    print(f"report: {path}")
    return 0 if summary.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
