"""The approval queue (decision #40): today's best jobs, each with a checked resume, waiting for FL.

    uv run python -m agents.application_queue build            # pick and prepare today's batch
    uv run python -m agents.application_queue approve 1 3 5    # these numbers, today's batch
    uv run python -m agents.application_queue pass 2 --reason "not the right industry"
    uv run python -m agents.application_queue applied 1        # after it really went out

Code picks the jobs: best score first, one job per company, never the same job twice, even when
two boards spell the company differently. Approving writes a submit pack: the PDF plus answers read
from the Applicant Profile. Questions code can't answer are listed for FL, never guessed. This
module fills in no form and submits nothing; that happens from the claude.ai Project, after FL
says so a second time (decision #10). A batch built from the fictional sample profile can be
approved so the flow can be tried, but it can never be marked applied.
"""

import argparse
import json
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg

from agents.fit_scoring import load_rules, load_vocabulary, profile_fingerprint
from agents.jd_analysis import load_scope
from agents.llm import AnthropicClient, LlmClient, LlmError
from agents.profile import Profile, load_profile
from agents.resume_doc import ResumeFormatError
from agents.skills import load_skill
from agents.tailor import OUT_DIR, Job, Tailored, scored_jobs, store, tailor_job
from pipeline.config import REPO_ROOT, LlmSettings, llm_settings, profile_dir

RULES_FILE = REPO_ROOT / "config" / "queue.toml"
QUEUE_DIR = REPO_ROOT / "output" / "queue"
SAMPLE_PACK_PREFIX = "SAMPLE_DO_NOT_SUBMIT_"
# Words that don't tell two companies apart: "Cheil" and "Cheil Worldwide" are one company.
COMPANY_NOISE = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "bv",
    "holdings",
    "holding",
    "group",
    "worldwide",
    "global",
    "the",
    "usa",
    "us",
    "technologies",
    "technology",
    "solutions",
    "careers",
}
# Which status may follow which. Anything else is refused.
NEXT_STATUS = {
    "approved": {"awaiting_approval"},
    "passed": {"awaiting_approval", "approved"},
    "applied": {"approved"},
}


class QueueError(ValueError):
    """A queue command that can't be done: an unknown number, or a step out of order."""


@dataclass(frozen=True)
class QueueRules:
    version: int
    daily_jobs: int
    per_company: int
    sites: dict[str, tuple[str, ...]]
    never_guess: tuple[re.Pattern[str], ...]
    fields: tuple[tuple[re.Pattern[str], str, str], ...]


def load_queue_rules(path: Path = RULES_FILE) -> QueueRules:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    answers = data["answers"]
    return QueueRules(
        version=int(data["version"]),
        daily_jobs=int(data["daily_jobs"]),
        per_company=int(data["per_company"]),
        sites={kind: tuple(ends) for kind, ends in data["sites"].items()},
        never_guess=tuple(re.compile(p, re.IGNORECASE) for p in answers["never_guess"]),
        fields=tuple(
            (re.compile(f["pattern"], re.IGNORECASE), f["field"], f["label"])
            for f in answers["fields"]
        ),
    )


# ---------------------------------------------------------------- picking the jobs


def company_key(company: str) -> str:
    words = re.findall(r"[a-z0-9]+", company.lower())
    kept = [word for word in words if word not in COMPANY_NOISE]
    return " ".join(kept or words)


def _title_words(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def application_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def job_keys(brief: dict[str, Any]) -> tuple[str, str]:
    """(same company + title, same title + site): either one matching means the same job. The
    second catches a company spelled two ways, such as a hospital and its initials."""
    title = _title_words(brief["title"])
    host = application_host(brief.get("url", ""))
    return f"{company_key(brief['company'])}|{title}", f"{title}|{host}"


def site_kind(url: str, rules: QueueRules) -> str:
    host = application_host(url)
    for kind, ends in rules.sites.items():
        if any(host == end or host.endswith(f".{end}") for end in ends):
            return kind
    return "unknown"


@dataclass(frozen=True)
class Batch:
    chosen: list[Job]
    skipped: list[tuple[Job, str]]


def pick_batch(
    jobs: list[Job],
    rules: QueueRules,
    seen_posting_ids: set[int],
    seen_job_keys: set[str],
    seen_title_keys: set[str],
) -> Batch:
    """The best scored jobs for one batch. `seen_*` are what earlier batches already queued. Every
    job left out for a reason is reported, so nothing quietly disappears."""
    chosen: list[Job] = []
    skipped: list[tuple[Job, str]] = []
    companies: dict[str, int] = {}
    job_seen, title_seen = set(seen_job_keys), set(seen_title_keys)
    worth = [job for job in jobs if job.fit["decision"] != "skip"]
    for job in sorted(worth, key=lambda j: (-j.fit["score"], j.posting_version_id)):
        job_key, title_key = job_keys(job.brief)
        company = company_key(job.brief["company"])
        if job.posting_version_id in seen_posting_ids:
            continue
        if job_key in job_seen or title_key in title_seen:
            skipped.append((job, "和已经排进队列的职位是同一个"))
            job_seen.add(job_key)
            title_seen.add(title_key)
            continue
        job_seen.add(job_key)
        title_seen.add(title_key)
        if len(chosen) >= rules.daily_jobs:
            continue
        if companies.get(company, 0) >= rules.per_company:
            skipped.append((job, "这批已经有这家公司的职位了"))
            continue
        companies[company] = companies.get(company, 0) + 1
        chosen.append(job)
    return Batch(chosen, skipped)


# ---------------------------------------------------------------- answers for the form


def _profile_value(applicant: dict[str, Any], field: str) -> Any:
    section, key = field.split(".")
    return applicant[section][key]


def _shown(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def answer_questions(
    questions: list[str], applicant: dict[str, Any], rules: QueueRules
) -> tuple[list[dict[str, str]], list[str]]:
    """Answers code can read from the profile, and the questions left for FL. Experience claims
    are never answered here, even when another part of the question matches."""
    answered, for_fl = [], []
    for question in questions:
        if any(pattern.search(question) for pattern in rules.never_guess):
            for_fl.append(question)
            continue
        hits = [
            f"{label}: {_shown(_profile_value(applicant, field))}"
            for pattern, field, label in rules.fields
            if pattern.search(question)
        ]
        if hits:
            answered.append({"question": question, "answer": "; ".join(hits)})
        else:
            for_fl.append(question)
    return answered, for_fl


def standard_answers(applicant: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """What most forms ask, from the Applicant Profile. Only compensation's target goes on forms."""
    pay = applicant["compensation"]
    return {
        "contact": applicant["contact"],
        "links": applicant["links"],
        "work_authorization": applicant["work_authorization"],
        "availability": applicant["availability"],
        "compensation": {
            "currency": pay["currency"],
            "base_salary_target": pay["base_salary_target"],
        },
        "location": applicant["location"],
        "background": applicant["background"],
        "eeo": applicant["eeo"],
    }


# ---------------------------------------------------------------- storing


def make_snapshot(tailored: Tailored, rules: QueueRules, resume_folder: Path) -> dict[str, Any]:
    brief, fit = tailored.job.brief, tailored.job.fit
    rounds = [entry for entry in tailored.history if "round" in entry]
    return {
        "company": brief["company"],
        "title": brief["title"],
        "url": brief.get("url", ""),
        "site": site_kind(brief.get("url", ""), rules),
        "score": fit["score"],
        "decision": fit["decision"],
        "work_mode": fit["work_mode"],
        "location": fit["location"],
        "gaps": fit["not_covered"],
        "nice_missing": fit["nice_missing"],
        "seven_second": rounds[-1]["seven_second_answer"] if rounds else "",
        "resume_status": tailored.status,
        "problems": tailored.all_problems,
        "pdf": str(tailored.pdf),
        "review_page": str(resume_folder / "review.html"),
        "cost_usd": round(tailored.cost_usd, 4),
        "questions": brief.get("knockout_questions_likely", []),
    }


def queue_job(
    conn: psycopg.Connection,
    tailored: Tailored,
    number: int,
    batch_date: date,
    profile: Profile,
    fingerprint: str,
    rules: QueueRules,
) -> None:
    brief = tailored.job.brief
    job_key, title_key = job_keys(brief)
    snapshot = make_snapshot(tailored, rules, tailored.pdf.parent)
    posting_version_id = tailored.job.posting_version_id
    with conn.transaction():
        conn.execute(
            "insert into agents.queue_items (posting_version_id, batch_date, batch_number, sample,"
            " profile_fingerprint, rules_version, company_key, job_key, title_key, snapshot)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                posting_version_id,
                batch_date,
                number,
                profile.bank.sample,
                fingerprint,
                rules.version,
                company_key(brief["company"]),
                job_key,
                title_key,
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        conn.execute(
            "insert into agents.application_events (posting_version_id, status) values (%s, %s)",
            (posting_version_id, "awaiting_approval"),
        )


def _seen(conn: psycopg.Connection) -> tuple[set[int], set[str], set[str]]:
    rows = conn.execute(
        "select posting_version_id, job_key, title_key from agents.queue_items"
    ).fetchall()
    return {r[0] for r in rows}, {r[1] for r in rows}, {r[2] for r in rows}


def batch_rows(conn: psycopg.Connection, batch_date: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select batch_number, posting_version_id, sample, status, reason, snapshot"
        " from agents.applications where batch_date = %s order by batch_number",
        (batch_date,),
    ).fetchall()
    keys = ("number", "posting_version_id", "sample", "status", "reason", "snapshot")
    return [dict(zip(keys, row, strict=True)) for row in rows]


def still_open(conn: psycopg.Connection, jobs: list[Job], today: date, days: int) -> list[Job]:
    """Only jobs seen on their board lately: a closed job can't be applied to."""
    rows = conn.execute(
        "select distinct p.posting_version_id from raw.job_postings p"
        " join raw.job_sightings s on s.source = p.source and s.company = p.company"
        "  and s.source_job_id = p.source_job_id"
        " where p.posting_version_id = any(%s) and s.seen_on >= %s::date - %s::int",
        ([job.posting_version_id for job in jobs], today, days),
    ).fetchall()
    open_ids = {row[0] for row in rows}
    return [job for job in jobs if job.posting_version_id in open_ids]


def build_batch(
    conn: psycopg.Connection,
    client: LlmClient,
    profile: Profile,
    folder: Path,
    settings: LlmSettings,
    batch_date: date,
    rules: QueueRules | None = None,
    size: int | None = None,
    out: Path = OUT_DIR,
) -> tuple[list[Tailored], list[tuple[Job, str]], list[str]]:
    """Prepare a batch for this date: pick, tailor, queue. A date that already has a batch gets no
    new jobs, so a second run changes nothing and costs nothing. A job the LLM can't finish is
    reported, and the next job doesn't take its place: the batch stays what FL was told."""
    from agents.tailor_review import write_job_files

    rules = rules or load_queue_rules()
    if size is not None:
        rules = QueueRules(**{**rules.__dict__, "daily_jobs": size})
    if batch_rows(conn, batch_date):
        return [], [], []
    vocab = load_vocabulary()
    jobs = scored_jobs(conn, profile, load_rules(), vocab, settings, batch_date)
    jobs = still_open(conn, jobs, batch_date, load_scope().open_within_days)
    batch = pick_batch(jobs, rules, *_seen(conn))
    drafter, reviewer = load_skill("resume-tailoring"), load_skill("resume-reviewer")
    fingerprint = profile_fingerprint(folder)
    results: list[Tailored] = []
    failed: list[str] = []
    for number, job in enumerate(batch.chosen, start=1):
        try:
            tailored = tailor_job(
                conn, client, job, profile, vocab, settings, drafter, reviewer, out
            )
        except (LlmError, ResumeFormatError) as exc:
            failed.append(f"#{job.posting_version_id} {job.brief['company']}: {exc}")
            continue
        store(conn, tailored, fingerprint, settings, drafter, reviewer)
        write_job_files(tailored, out)
        queue_job(conn, tailored, number, batch_date, profile, fingerprint, rules)
        results.append(tailored)
    return results, batch.skipped, failed


# ---------------------------------------------------------------- FL's decisions


def set_status(
    conn: psycopg.Connection,
    batch_date: date,
    numbers: list[int],
    status: str,
    reason: str | None = None,
) -> list[dict[str, Any]]:
    """Record FL's decision for these numbers: all of them or none. Refuses a step out of order,
    and refuses to mark anything from the fictional profile as applied."""
    rows = {row["number"]: row for row in batch_rows(conn, batch_date)}
    for number in numbers:
        row = rows.get(number)
        if row is None:
            raise QueueError(f"no job number {number} in the {batch_date} batch")
        if status == "applied" and row["sample"]:
            raise QueueError(
                f"number {number} was built from the fictional sample profile; it must never be "
                "sent to a real company, so it can't be marked applied"
            )
        if row["status"] not in NEXT_STATUS[status]:
            raise QueueError(f"number {number} is {row['status']}; it can't become {status}")
    with conn.transaction():
        for number in numbers:
            conn.execute(
                "insert into agents.application_events (posting_version_id, status, reason)"
                " values (%s, %s, %s)",
                (rows[number]["posting_version_id"], status, reason),
            )
    return batch_rows(conn, batch_date)


def write_pack(
    rows: list[dict[str, Any]], batch_date: date, profile: Profile, rules: QueueRules, out: Path
) -> Path | None:
    """The submit pack for the approved jobs: their PDFs and one file of answers, to take to the
    claude.ai Project. From the fictional profile it is named so nobody can mistake it."""
    from agents.queue_review import pack_markdown

    approved = [row for row in rows if row["status"] == "approved"]
    if not approved:
        return None
    sample = any(row["sample"] for row in approved)
    folder = out / str(batch_date) / f"{SAMPLE_PACK_PREFIX if sample else ''}submit_pack"
    folder.mkdir(parents=True, exist_ok=True)
    for row in approved:
        pdf = Path(row["snapshot"]["pdf"])
        if pdf.is_file():
            shutil.copy2(pdf, folder / pdf.name)
    pack = folder / f"{SAMPLE_PACK_PREFIX if sample else ''}submit_pack.md"
    pack.write_text(pack_markdown(approved, batch_date, profile.applicant, rules), encoding="utf-8")
    return pack


# ---------------------------------------------------------------- command line


def _today() -> date:
    from pipeline.daily import report_timezone

    return datetime.now(report_timezone()).date()


def main(argv: list[str] | None = None) -> int:
    from agents.queue_review import write_page
    from pipeline.db import connect, migrate

    parser = argparse.ArgumentParser(prog="python -m agents.application_queue")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="pick and prepare a batch")
    build.add_argument("--n", type=int, help="jobs in this batch, instead of config/queue.toml")
    for name, helptext in (
        ("approve", "approve these numbers; writes the submit pack"),
        ("pass", "leave these numbers out"),
        ("applied", "these numbers really went out"),
    ):
        command = commands.add_parser(name, help=helptext)
        command.add_argument("numbers", nargs="+", type=int)
        command.add_argument("--reason")
    for command in commands.choices.values():
        command.add_argument("--date", type=date.fromisoformat, help="default: today")
        command.add_argument("--out", type=Path, default=QUEUE_DIR)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    batch_date = args.date or _today()
    settings, folder = llm_settings(), profile_dir()
    profile, rules = load_profile(folder), load_queue_rules()
    with connect() as conn:
        migrate(conn)
        skipped: list[tuple[Job, str]] = []
        if args.command == "build":
            results, skipped, failed = build_batch(
                conn, AnthropicClient(), profile, folder, settings, batch_date, rules, args.n
            )
            for line in failed:
                print(f"FAILED {line}")
            paid = sum(t.paid_now_usd for t in results)
            print(f"{len(results)} new in the {batch_date} batch; paid ${paid:.2f}")
        else:
            status = {"approve": "approved", "pass": "passed", "applied": "applied"}[args.command]
            try:
                set_status(conn, batch_date, args.numbers, status, args.reason)
            except QueueError as exc:
                print(f"REFUSED {exc}")
                return 1
        rows = batch_rows(conn, batch_date)
        for row in rows:
            snap = row["snapshot"]
            print(
                f"{row['number']}. {row['status']:18} {snap['score']:3d} {snap['company']} | "
                f"{snap['title']} [{snap['site']}]"
            )
        pack = write_pack(rows, batch_date, profile, rules, args.out)
        if pack:
            print(f"submit pack: {pack}")
        if rows:
            print(f"page: {write_page(rows, skipped, batch_date, args.out, pack)}")
        else:
            print("no jobs to queue yet: new briefs arrive with the next daily run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
