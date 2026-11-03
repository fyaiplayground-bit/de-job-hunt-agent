"""Does the pipeline have a job FL found somewhere else, e.g. on LinkedIn? (decision #34)

    uv run python -m pipeline.find_job "Voto Consulting" "Java Backend Developer"
    uv run python -m pipeline.find_job "Sigma Computing" "data engineer" --note "seen on LinkedIn"
    uv run python -m pipeline.find_job --stats

Looks through every stored posting by company and title words. When the job isn't there, one
live freehire search (honest client, one request) tells whether freehire has it at all, and the
answer is the most likely reason it was missed. Every check is logged in ops.coverage_checks, so
found / checked is the pipeline's measured recall and the reasons say what to fix.
"""

import argparse
import re
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from agents.jd_analysis import Scope, load_scope
from pipeline.config import REPO_ROOT
from pipeline.safety_gate import GATE_VERSION

COMPANIES_FILE = REPO_ROOT / "config" / "companies.toml"
SEARCHES_FILE = REPO_ROOT / "config" / "searches.toml"
LEGAL_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "plc", "gmbh", "the"}
FREEHIRE_LOOKBACK_DAYS = 60

REASON_TEXT = {
    "found": "stored by the pipeline",
    "freehire_title": "freehire has it, but the title is outside our freehire search terms "
                      "(widen config/searches.toml)",
    "freehire_missed": "freehire has it and the title fits our search: probably posted before "
                       "our window, or beyond the page cap",
    "board_missing": "the company is one of our boards, but this job isn't stored (new since "
                     "the last run, or already closed)",
    "not_in_freehire": "none of our sources has it (needs another source: the company's board, "
                       "or LinkedIn)",
    "unknown": "not stored, and the live freehire check couldn't settle it (the check failed, "
               "or freehire returned too many results to be sure)",
}
FREEHIRE_PAGES = 3  # the live check reads at most this many pages of 100


def normalize_company(name: str) -> str:
    """"Voto Consulting, LLC" -> "votoconsulting": lowercase letters and digits, legal suffixes
    dropped, so board tokens, slugs and display names compare equal."""
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()
    return "".join(w for w in words if w not in LEGAL_SUFFIXES)


def title_words(title: str) -> list[str]:
    return re.sub(r"[^a-z0-9+# ]+", " ", title.lower()).split()


def search_terms(path: Path = SEARCHES_FILE) -> list[list[str]]:
    """Our freehire title terms as word lists ("title:data engineer" -> [data, engineer])."""
    terms = []
    for search in tomllib.loads(path.read_text(encoding="utf-8")).get("freehire", []):
        for alternative in search["query"].split(" OR "):
            terms.append(title_words(alternative.replace("title:", "")))
    return terms


def board_companies(path: Path = COMPANIES_FILE) -> set[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {normalize_company(token) for section in data.values() for token in section["boards"]}


def has_phrase(title: str, words: list[str]) -> bool:
    """The words appear in the title in this order, next to each other (punctuation ignored):
    "data engineer" matches "Sr. Data Engineer, Platform", not "Data Center Engineer"."""
    return f" {' '.join(words)} " in f" {' '.join(title_words(title))} "


def title_fits(title: str, terms: list[list[str]]) -> bool:
    words = set(title_words(title))
    return any(set(term) <= words for term in terms)


@dataclass
class Match:
    posting_version_id: int
    source: str
    company: str
    title: str
    first_seen: date | None
    last_seen: date | None
    triage: str | None
    briefed: bool
    not_analyzed_because: list[str] = field(default_factory=list)  # [] = in the analysis scope

    def as_json(self) -> dict[str, Any]:
        return {
            "posting_version_id": self.posting_version_id, "source": self.source,
            "company": self.company, "title": self.title,
            "first_seen": str(self.first_seen), "last_seen": str(self.last_seen),
            "triage": self.triage, "briefed": self.briefed,
        }


def _pg_to_python(pattern: str) -> str:
    """The scope's Postgres word boundaries (\\m, \\M) as Python's \\b."""
    return pattern.replace(r"\m", r"\b").replace(r"\M", r"\b")


def scope_reasons(
    scope: Scope, title: str, triage: str | None, stale: bool, text_chars: int,
    last_seen: date | None, today: date,
) -> list[str]:
    """Why a stored posting is outside the analysis scope (config/analysis_scope.toml)."""
    reasons = []
    if not re.search(_pg_to_python(scope.title_include), title, re.I):
        reasons.append("title doesn't look like DE")
    if re.search(_pg_to_python(scope.title_exclude), title, re.I):
        reasons.append("title level excluded (staff/lead/manager/...)")
    if triage not in scope.triage_allowed:
        reasons.append(f"gate triage {triage}")
    if scope.skip_freehire_stale and stale:
        reasons.append("freehire marks it stale")
    if text_chars < scope.min_text_chars:
        reasons.append(f"text only {text_chars} characters (cut-off snippet)")
    if last_seen is None or (today - last_seen).days > scope.open_within_days:
        reasons.append(f"not seen on its board since {last_seen}")
    return reasons


STORED_SQL = """
with latest as (
    select distinct on (p.source, p.company, p.source_job_id)
           p.posting_version_id, p.source, p.company, p.source_job_id, p.payload,
           coalesce(p.payload->>'title', p.payload->>'text', '') as title
    from raw.job_postings p
    order by p.source, p.company, p.source_job_id, p.posting_version_id desc
)
select l.posting_version_id, l.source,
       coalesce(l.payload->>'company_name', l.payload->>'company', l.company) as display,
       l.company, l.title,
       (select min(s.seen_on) from raw.job_sightings s where s.source = l.source
          and s.company = l.company and s.source_job_id = l.source_job_id),
       (select max(s.seen_on) from raw.job_sightings s where s.source = l.source
          and s.company = l.company and s.source_job_id = l.source_job_id),
       g.triage, coalesce(length(g.cleaned_text), 0),
       coalesce(l.payload->'reality'->>'class', '') = 'stale',
       exists (select 1 from agents.jd_briefs b where b.posting_version_id = l.posting_version_id)
from latest l
left join gate.results g
  on g.posting_version_id = l.posting_version_id and g.gate_version = %(gate)s
where l.title ilike all(%(words)s)
order by l.posting_version_id desc
"""


def find_stored(
    conn: psycopg.Connection, company: str, title: str, scope: Scope, today: date
) -> list[Match]:
    """Stored postings (latest version per job) whose company starts with the normalized name
    and whose title has every word of `title`."""
    wanted = normalize_company(company)
    words = title_words(title)
    matches = []
    rows = conn.execute(
        STORED_SQL, {"gate": GATE_VERSION, "words": [f"%{w}%" for w in words] or ["%"]}
    ).fetchall()
    for row in rows:
        (pvid, source, display, slug, job_title, first, last, triage, chars, stale, briefed) = row
        names = {normalize_company(display or ""), normalize_company(slug)}
        if not any(n.startswith(wanted) for n in names if n) or not has_phrase(job_title, words):
            continue
        matches.append(Match(
            posting_version_id=pvid, source=source, company=display or slug, title=job_title,
            first_seen=first, last_seen=last, triage=triage, briefed=briefed,
            not_analyzed_because=scope_reasons(scope, job_title, triage, stale, chars, last, today),
        ))
    return matches


def freehire_search(company: str, title: str) -> tuple[list[dict[str, Any]], bool]:
    """A live freehire search (US, last 60 days, at most 3 pages): the company's name as free
    text plus the title words, filtered to that company. freehire has no company filter, so the
    second value says whether the results ran out (True) or the page limit cut them (False)."""
    from ingestion.context import FetchContext
    from ingestion.freehire import fetch_jobs
    from ingestion.http import make_client

    with make_client() as client:
        ctx = FetchContext(client=client, options={
            "query": f"{company} title:{title}", "countries": ["us"],
            "posted_within_days": FREEHIRE_LOOKBACK_DAYS, "page_size": 100,
            "max_pages": FREEHIRE_PAGES,
        })
        jobs = fetch_jobs(ctx, "coverage-check")
    return _freehire_matches(jobs, company, title), len(jobs) < 100 * FREEHIRE_PAGES


def _freehire_matches(jobs: list[dict[str, Any]], company: str, title: str) -> list[dict]:
    """freehire's own title filter isn't reliable with extra free text, so filter here too."""
    wanted, words = normalize_company(company), title_words(title)
    return [
        {"title": j.get("title"), "company": j.get("company"), "posted_at": j.get("posted_at"),
         "ats": j.get("source"), "url": j.get("url")}
        for j in jobs
        if has_phrase(str(j.get("title") or ""), words)
        and any(normalize_company(str(j.get(k) or "")).startswith(wanted)
                for k in ("company", "company_slug"))
    ]


@dataclass
class CheckResult:
    found: bool
    reason: str
    matches: list[Match]
    freehire_matches: list[dict[str, Any]] | None
    coverage_check_id: int | None = None


def check(
    conn: psycopg.Connection,
    company: str,
    title: str,
    note: str | None = None,
    freehire: Callable[[str, str], tuple[list[dict[str, Any]], bool]] = freehire_search,
    today: date | None = None,
    scope: Scope | None = None,
    terms: list[list[str]] | None = None,
    boards: set[str] | None = None,
) -> CheckResult:
    """Look for the job, explain a miss, and log the check."""
    today = today or date.today()
    matches = find_stored(conn, company, title, scope or load_scope(), today)
    fh: list[dict[str, Any]] | None = None
    if matches:
        reason = "found"
    else:
        boards = boards if boards is not None else board_companies()
        try:
            fh, complete = freehire(company, title)
        except Exception:  # a failed live check must not lose the logged question
            reason = "unknown"
        else:
            if fh:
                fits = any(title_fits(str(j["title"]), terms or search_terms()) for j in fh)
                reason = "freehire_missed" if fits else "freehire_title"
            elif normalize_company(company) in boards:
                reason = "board_missing"
            elif complete:
                reason = "not_in_freehire"
            else:
                reason = "unknown"  # not in the pages we read, but there were more
    result = CheckResult(bool(matches), reason, matches, fh)
    result.coverage_check_id = conn.execute(
        "insert into ops.coverage_checks (company_query, title_query, found, reason, matches,"
        " freehire_matches, note) values (%s, %s, %s, %s, %s, %s, %s)"
        " returning coverage_check_id",
        (company, title, result.found, reason, Jsonb([m.as_json() for m in matches]),
         None if fh is None else Jsonb(fh), note),
    ).fetchone()[0]
    return result


def format_result(company: str, title: str, result: CheckResult) -> str:
    lines = [f'{"FOUND" if result.found else "NOT FOUND"}: "{company}" / "{title}"']
    for m in result.matches:
        status = (
            "briefed" if m.briefed else
            "in analysis scope, not briefed yet" if not m.not_analyzed_because else
            "not analyzed: " + "; ".join(m.not_analyzed_because)
        )
        lines.append(
            f"  - [{m.source} #{m.posting_version_id}] {m.company} | {m.title} | seen "
            f"{m.first_seen} → {m.last_seen} | gate {m.triage} | {status}"
        )
    if not result.found:
        lines.append(f"  likely reason: {REASON_TEXT[result.reason]}")
        shown = (result.freehire_matches or [])[:10]
        for j in shown:
            lines.append(
                f"  - freehire: {j['company']} | {j['title']} | posted {j['posted_at']} | "
                f"via {j['ats']}"
            )
        more = len(result.freehire_matches or []) - len(shown)
        if more > 0:
            lines.append(f"  - …and {more} more on freehire")
    lines.append(f"  (logged as coverage check #{result.coverage_check_id})")
    return "\n".join(lines)


def stats(conn: psycopg.Connection) -> str:
    rows = conn.execute(
        "select reason, count(*) from ops.coverage_checks group by 1 order by 2 desc"
    ).fetchall()
    total = sum(n for _, n in rows)
    if not total:
        return "no coverage checks yet"
    found = sum(n for reason, n in rows if reason == "found")
    lines = [f"coverage: {found}/{total} found ({100 * found / total:.0f}%)"]
    lines += [f"  {reason}: {n} — {REASON_TEXT[reason]}" for reason, n in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.find_job")
    parser.add_argument("company", nargs="?")
    parser.add_argument("title", nargs="?", help="words from the job title")
    parser.add_argument("--note", help="where FL saw it, e.g. a LinkedIn URL")
    parser.add_argument("--stats", action="store_true", help="coverage so far")
    args = parser.parse_args(argv)
    if not args.stats and not (args.company and args.title):
        parser.error("give a company and title words, or --stats")

    from pipeline.db import connect, migrate

    with connect() as conn:
        migrate(conn)
        if args.stats:
            print(stats(conn))
            return 0
        result = check(conn, args.company, args.title, note=args.note)
        print(format_result(args.company, args.title, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
