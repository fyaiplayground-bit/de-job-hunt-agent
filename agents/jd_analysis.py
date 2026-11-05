"""jd-analysis (Agent 1, decision #31): turn each in-scope DE posting into a structured brief.

    uv run python -m agents.jd_analysis run --dry-run     # how many postings, rough cost, no calls
    uv run python -m agents.jd_analysis run --limit 20    # analyze up to 20 not yet analyzed
    uv run python -m agents.jd_analysis show 12345        # print one stored brief

Code picks the postings (config/analysis_scope.toml), the LLM reads one posting's cleaned text
and answers in BRIEF_SCHEMA, and code adds company, title and URL from the raw posting. Answers
are cached by agents.llm (decision #30), so a re-run costs nothing.
"""

import argparse
import json
import sys
import tomllib
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from agents.llm import (
    AnthropicClient,
    LlmClient,
    LlmError,
    LlmRequest,
    ask,
    build_request,
    cost_usd,
)
from agents.skills import Skill, load_skill
from pipeline.config import REPO_ROOT, LlmSettings, llm_settings
from pipeline.safety_gate import GATE_VERSION

SCOPE_FILE = REPO_ROOT / "config" / "analysis_scope.toml"

_TEXTS = {"type": "array", "items": {"type": "string"}}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# What the LLM must return. Every field is required (null or [] when the posting says nothing),
# so code never has to guess whether a field was skipped or empty.
BRIEF_SCHEMA = _object({
    "archetype": {"type": "string", "enum": ["analytics_engineer", "pipeline_de", "infra_de"]},
    "seniority": {"type": "string", "enum": ["junior", "mid", "senior", "staff_plus", "unclear"]},
    "years_required": {"type": ["integer", "null"]},
    "must_haves": {"type": "array", "items": _object({
        "skill": {"type": "string"},
        "exact_phrases": _TEXTS,
        "weight": {"type": "string", "enum": ["core", "normal"]},
    })},
    "nice_to_haves": {"type": "array", "items": _object({
        "skill": {"type": "string"},
        "exact_phrases": _TEXTS,
    })},
    "work_mode": {"type": "string", "enum": ["remote", "hybrid", "onsite", "unclear"]},
    "locations": _TEXTS,
    "remote_regions": _TEXTS,
    "salary": _object({
        "min": {"type": ["number", "null"]},
        "max": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
    }),
    "sponsorship": {"type": "string", "enum": ["available", "not_available", "unstated"]},
    "hidden_signals": _TEXTS,
    "knockout_questions_likely": _TEXTS,
    "safety_flags": _TEXTS,
})

# For the dry-run estimate only: output tokens (thinking + JSON) assumed per posting.
ESTIMATED_OUTPUT_TOKENS = 2500


@dataclass(frozen=True)
class Scope:
    version: int
    title_include: str
    title_exclude: str
    open_within_days: int
    triage_allowed: tuple[str, ...]
    skip_freehire_stale: bool
    min_text_chars: int = 0  # shorter cleaned text is a cut-off snippet, not a posting


def load_scope(path: Path = SCOPE_FILE) -> Scope:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Scope(
        version=int(data["version"]),
        title_include=data["title_include"],
        title_exclude=data["title_exclude"],
        open_within_days=int(data["open_within_days"]),
        triage_allowed=tuple(data["triage_allowed"]),
        skip_freehire_stale=bool(data["skip_freehire_stale"]),
        min_text_chars=int(data.get("min_text_chars", 0)),
    )


@dataclass(frozen=True)
class Candidate:
    posting_version_id: int
    source: str
    company: str
    title: str
    location: str
    url: str
    cleaned_text: str

    def data(self) -> str:
        """What the LLM reads: company and title, then the gate's cleaned text. The board's
        location is left out on purpose: it goes into the brief from code, and copies of one
        job posted in several cities then make the same request, answered once from the cache."""
        return f"Company: {self.company}\nTitle: {self.title}\n\n{self.cleaned_text}"


def _display_fields(source: str, company: str, payload: dict[str, Any]) -> tuple[str, str, str]:
    """(company name, location, URL) as each source's API spells them."""
    if source == "greenhouse":
        location = (payload.get("location") or {}).get("name", "")
        return payload.get("company_name") or company, location, payload.get("absolute_url", "")
    if source == "lever":
        categories = payload.get("categories") or {}
        location = categories.get("location", "")
        if payload.get("workplaceType") and payload["workplaceType"] not in location.lower():
            location = f"{location} ({payload['workplaceType']})".strip()
        return company, location, payload.get("hostedUrl", "")
    location = payload.get("location") or ""
    if payload.get("work_mode"):
        location = f"{location} ({payload['work_mode']})".strip()
    name = payload.get("company") if isinstance(payload.get("company"), str) else company
    return name or company, location, payload.get("url", "")


CANDIDATES_SQL = """
with chosen as (
    select p.posting_version_id, p.source, p.company, p.source_job_id, p.payload,
           coalesce(p.payload->>'title', p.payload->>'text', '') as title
    from dedupe.jobs j
    join raw.job_postings p on p.posting_version_id = j.chosen_posting_version_id
)
select c.posting_version_id, c.source, c.company, c.title, c.payload, g.cleaned_text,
       exists (
           select 1 from agents.jd_briefs b
           where b.posting_version_id = c.posting_version_id
             and b.prompt_version = %(prompt_version)s and b.model = %(model)s
       ) as done
from chosen c
join gate.results g
  on g.posting_version_id = c.posting_version_id and g.gate_version = %(gate_version)s
where c.title ~* %(include)s
  and c.title !~* %(exclude)s
  and g.triage = any(%(triage)s)
  and length(g.cleaned_text) >= %(min_chars)s
  and not (%(skip_stale)s and c.source = 'freehire'
           and coalesce(c.payload->'reality'->>'class', '') = 'stale')
  and exists (
      select 1 from raw.job_sightings s
      where s.source = c.source and s.company = c.company and s.source_job_id = c.source_job_id
        and s.seen_on >= current_date - %(days)s
  )
order by c.posting_version_id desc
"""


def select_candidates(
    conn: psycopg.Connection,
    scope: Scope,
    prompt_version: str,
    model: str,
    only: Collection[int] | None = None,
) -> tuple[list[Candidate], int]:
    """In-scope postings not yet briefed by this prompt version and model, newest first, and
    how many in-scope postings already have a brief. `only` limits both to those posting
    versions (the daily run passes the jobs it found new)."""
    rows = conn.execute(CANDIDATES_SQL, {
        "prompt_version": prompt_version, "model": model, "gate_version": GATE_VERSION,
        "include": scope.title_include, "exclude": scope.title_exclude,
        "triage": list(scope.triage_allowed), "skip_stale": scope.skip_freehire_stale,
        "days": scope.open_within_days, "min_chars": scope.min_text_chars,
    }).fetchall()
    wanted = None if only is None else set(only)
    todo, done = [], 0
    for posting_version_id, source, company, title, payload, cleaned_text, is_done in rows:
        if wanted is not None and posting_version_id not in wanted:
            continue
        if is_done:
            done += 1
            continue
        name, location, url = _display_fields(source, company, payload)
        todo.append(Candidate(posting_version_id, source, name, title, location, url, cleaned_text))
    return todo, done


def candidates_by_id(conn: psycopg.Connection, ids: Collection[int]) -> list[Candidate]:
    rows = conn.execute(
        "select p.posting_version_id, p.source, p.company,"
        " coalesce(p.payload->>'title', p.payload->>'text', ''), p.payload, g.cleaned_text"
        " from raw.job_postings p join gate.results g"
        "   on g.posting_version_id = p.posting_version_id and g.gate_version = %s"
        " where p.posting_version_id = any(%s) order by p.posting_version_id",
        (GATE_VERSION, list(ids)),
    ).fetchall()
    candidates = []
    for posting_version_id, source, company, title, payload, cleaned_text in rows:
        name, location, url = _display_fields(source, company, payload)
        candidates.append(
            Candidate(posting_version_id, source, name, title, location, url, cleaned_text)
        )
    return candidates


def make_brief(candidate: Candidate, output: dict[str, Any]) -> dict[str, Any]:
    """The LLM's answer plus the facts code copies from the job board."""
    return {
        "company": candidate.company,
        "title": candidate.title,
        "url": candidate.url,
        "source": candidate.source,
        "board_location": candidate.location,
        **output,
    }


def brief_postings(
    conn: psycopg.Connection,
    client: LlmClient,
    settings: LlmSettings,
    skill: Skill,
    ids: Collection[int],
) -> tuple[dict[int, tuple[dict[str, Any], str]], float]:
    """Briefs under a prompt that may be only a proposal, for trying it on real jobs: posting
    version -> (brief, cleaned text), and what was paid. Nothing goes to agents.jd_briefs."""
    briefs, paid = {}, 0.0
    for candidate in candidates_by_id(conn, ids):
        request = build_request(skill, BRIEF_SCHEMA, candidate.data(), settings)
        result = ask(conn, client, request)
        paid += 0.0 if result.cached else result.cost_usd or 0.0
        briefs[candidate.posting_version_id] = (
            make_brief(candidate, result.output), candidate.cleaned_text
        )
    return briefs, paid


def estimate_cost(request: LlmRequest) -> float:
    """Rough: about 4 characters per token for input, ESTIMATED_OUTPUT_TOKENS out."""
    input_tokens = (len(request.system) + len(request.user)) // 4
    return cost_usd(request.model, input_tokens, ESTIMATED_OUTPUT_TOKENS) or 0.0


@dataclass
class RunSummary:
    in_scope: int = 0
    already_done: int = 0
    selected: int = 0
    analyzed: int = 0
    from_cache: int = 0
    cost_usd: float = 0.0
    estimated_usd: float = 0.0
    skipped_by_limit: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)
    must_have_counts: Counter[str] = field(default_factory=Counter)  # skill -> postings asking


def run(
    conn: psycopg.Connection,
    client: LlmClient | None,
    settings: LlmSettings,
    limit: int | None = None,
    dry_run: bool = False,
    scope: Scope | None = None,
    skill: Skill | None = None,
    only: Collection[int] | None = None,
) -> RunSummary:
    """Brief up to `limit` in-scope postings that don't have one yet (only those in `only`, when
    given). A posting the model can't brief (declined, cut off) is reported and skipped; the run
    goes on."""
    scope = scope or load_scope()
    skill = skill or load_skill("jd-analysis")
    todo, done = select_candidates(conn, scope, skill.prompt_version, settings.model, only)
    chosen = todo if limit is None else todo[:limit]
    summary = RunSummary(
        in_scope=len(todo) + done, already_done=done, selected=len(chosen),
        skipped_by_limit=len(todo) - len(chosen),
    )
    for candidate in chosen:
        request = build_request(skill, BRIEF_SCHEMA, candidate.data(), settings)
        if dry_run:
            summary.estimated_usd += estimate_cost(request)
            continue
        assert client is not None, "a live run needs a client"
        try:
            result = ask(conn, client, request)
        except LlmError as exc:
            summary.failed.append((candidate.posting_version_id, str(exc)))
            continue
        conn.execute(
            "insert into agents.jd_briefs (posting_version_id, prompt_version, model,"
            " scope_version, llm_call_id, brief) values (%s, %s, %s, %s, %s, %s)"
            " on conflict do nothing",
            (
                candidate.posting_version_id, skill.prompt_version, settings.model,
                scope.version, result.llm_call_id,
                json.dumps(make_brief(candidate, result.output), ensure_ascii=False),
            ),
        )
        summary.analyzed += 1
        summary.must_have_counts.update({m["skill"] for m in result.output["must_haves"]})
        if result.cached:
            summary.from_cache += 1
        else:
            summary.cost_usd += result.cost_usd or 0.0
    return summary


def format_summary(summary: RunSummary, dry_run: bool) -> str:
    lines = [
        f"in scope: {summary.in_scope} postings ({summary.already_done} already briefed)",
        f"selected this run: {summary.selected}",
    ]
    if dry_run:
        lines.append(f"estimated cost: ${summary.estimated_usd:.2f} (rough; nothing was called)")
    else:
        lines.append(
            f"briefed: {summary.analyzed} ({summary.from_cache} from cache), "
            f"cost ${summary.cost_usd:.2f}"
        )
        for posting_version_id, error in summary.failed:
            lines.append(f"  FAILED {posting_version_id}: {error}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.jd_analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="brief in-scope postings that have no brief yet")
    run_cmd.add_argument("--limit", type=int, help="at most this many postings")
    run_cmd.add_argument("--dry-run", action="store_true", help="count and estimate; no calls")
    show_cmd = commands.add_parser("show", help="print the stored brief(s) of one posting version")
    show_cmd.add_argument("posting_version_id", type=int)
    args = parser.parse_args(argv)

    from pipeline.db import connect, migrate

    settings = llm_settings()
    with connect() as conn:
        migrate(conn)
        if args.command == "show":
            rows = conn.execute(
                "select prompt_version, model, brief from agents.jd_briefs"
                " where posting_version_id = %s order by created_at",
                (args.posting_version_id,),
            ).fetchall()
            if not rows:
                print("no brief for that posting version")
                return 1
            for prompt_version, model, brief in rows:
                print(f"# {prompt_version} · {model}")
                print(json.dumps(brief, indent=2, ensure_ascii=False))
            return 0
        client = None if args.dry_run else AnthropicClient()
        summary = run(conn, client, settings, limit=args.limit, dry_run=args.dry_run)
        print(format_summary(summary, args.dry_run))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
