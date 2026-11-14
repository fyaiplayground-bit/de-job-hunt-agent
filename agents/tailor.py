"""resume-tailoring (Agent 4, decision #38): one job in, one checked one-page resume out.

    uv run python -m agents.tailor run --top 5 --dry-run   # which jobs, rough cost, no calls
    uv run python -m agents.tailor run --top 5             # the best scored jobs
    uv run python -m agents.tailor run 12345 12346         # these posting versions

The LLM writes content and code owns the facts: the drafter returns a headline, a summary, bullets
citing their evidence, and skills; code adds the name, titles, employers, dates and education from
the Evidence Bank and builds a resume.md. A second LLM with fresh context reviews it and returns
exact edits. Code applies each edit and rejects any that breaks a fact check. Then the page is
rendered, trimmed to one page, and checked. Run by hand, not in the daily run, until Milestone 5.
Answers are cached (decision #30), so a re-run costs nothing.
"""

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from agents.fit_scoring import (
    Rules,
    Vocabulary,
    load_briefs,
    load_rules,
    load_vocabulary,
    profile_fingerprint,
    score_brief,
)
from agents.jd_analysis import _object, brief_postings
from agents.llm import AnthropicClient, LlmClient, LlmError, LlmResult, ask, build_request
from agents.pdf_checks import PdfReport, check_pdf
from agents.profile import Profile, load_profile, resume_month
from agents.render_resume import render_pdf
from agents.resume_checks import Problems, check_draft, draft_bullets, mentions
from agents.resume_doc import ResumeFormatError, parse_resume
from agents.skills import Skill, load_skill, parse_skill
from pipeline.config import REPO_ROOT, LlmSettings, llm_settings, profile_dir

OUT_DIR = REPO_ROOT / "output" / "tailored"
TRIAL_DIR = REPO_ROOT / "output" / "tailored_trial"
MAX_REVIEW_ROUNDS = 2
MAX_TRIMS = 30
ESTIMATED_USD_PER_RESUME = 0.2  # for --dry-run only; the 2026-11-03 trial averaged $0.18

_TEXTS = {"type": "array", "items": {"type": "string"}}
_BULLETS = {
    "type": "array",
    "items": _object(
        {
            "where": {"type": "string"},
            "bullets": {
                "type": "array",
                "items": _object({"text": {"type": "string"}, "evidence": _TEXTS}),
            },
        }
    ),
}
DRAFT_SCHEMA = _object(
    {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "experience": _BULLETS,
        "projects": _BULLETS,
        "skills": _TEXTS,
        "changes": {
            "type": "array",
            "items": _object(
                {
                    "edit": {"type": "string"},
                    "serves": {"type": "string"},
                }
            ),
        },
    }
)
REVIEW_SCHEMA = _object(
    {
        "verdict": {"type": "string", "enum": ["pass", "revise"]},
        "seven_second_answer": {"type": "string"},
        "edits": {
            "type": "array",
            "items": _object(
                {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "replace",
                            "add_bullet",
                            "remove_bullet",
                            "move_first",
                            "add_skill",
                        ],
                    },
                    "where": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "evidence": _TEXTS,
                    "reason": {"type": "string"},
                }
            ),
        },
        "notes": _TEXTS,
    }
)


@dataclass(frozen=True)
class Job:
    posting_version_id: int
    brief: dict[str, Any]
    text: str  # the gate's cleaned posting
    fit: dict[str, Any]


class EditError(ValueError):
    """A reviewer's edit doesn't fit the draft: its text isn't there, or isn't there once."""


def _clean(text: str) -> str:
    return " ".join(text.split())


def clean_draft(output: dict[str, Any]) -> dict[str, Any]:
    """The drafter's answer with whitespace tidied, so a line break can't change the page."""
    draft = copy.deepcopy(output)
    draft["headline"] = _clean(draft["headline"])
    draft["summary"] = _clean(draft["summary"])
    draft["skills"] = [_clean(skill) for skill in draft["skills"]]
    for _, _, bullet in draft_bullets(draft):
        bullet["text"] = _clean(bullet["text"])
    return draft


def _web_address(url: str) -> str:
    return re.sub(r"^https?://", "", url).rstrip("/")


def build_resume(draft: dict[str, Any], profile: Profile) -> str:
    """A resume.md: code's facts around the LLM's text. Every role is listed; a project only when
    it has bullets."""
    bank, contact, links = profile.bank, profile.applicant["contact"], profile.applicant["links"]
    top = [f"{contact['city']}, {contact['state']}", contact["email"], contact["phone"]]
    top += [_web_address(links[key]) for key in ("portfolio", "linkedin", "github") if links[key]]

    def bullets(section: str, where: str) -> list[str]:
        return [
            f"- {b['text']}" for e in draft[section] if e["where"] == where for b in e["bullets"]
        ]

    lines = [
        f"# {contact['name']}",
        "",
        draft["headline"],
        " · ".join(top),
        "",
        "## Summary",
        "",
        draft["summary"],
        "",
        "## Experience",
        "",
    ]
    for role in bank.roles:
        end = resume_month(role.end) if role.end else "Present"
        place = f" · {role.location}" if role.location else ""  # a role may leave its city out
        lines += [f"**{role.title}** · {role.employer}{place}"]
        lines += [f"{resume_month(role.start)} - {end}", ""]
        lines += [*bullets("experience", role.id), ""]
    lines += ["## Projects", ""]
    for project in bank.projects:
        found = bullets("projects", project.id)
        if not found:
            continue
        status = " (in progress)" if project.status == "in_progress" else ""
        address = f" · {_web_address(project.url)}" if project.url else ""
        lines += [f"**{project.name}**{status}{address}", "", *found, ""]
    lines += ["## Skills", "", ", ".join(draft["skills"]), "", "## Education", ""]
    for school in bank.education:
        lines.append(f"**{school.degree}** · {school.school} · {resume_month(school.end)}")
    return "\n".join(lines) + "\n"


def _text_fields(draft: dict[str, Any]) -> list[tuple[dict[str, Any] | list[str], Any]]:
    """Every place a `replace` may touch, as (container, key)."""
    fields: list[tuple[Any, Any]] = [(draft, "headline"), (draft, "summary")]
    fields += [(bullet, "text") for _, _, bullet in draft_bullets(draft)]
    fields += [(draft["skills"], index) for index in range(len(draft["skills"]))]
    return fields


def _find_bullet(draft: dict[str, Any], text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    wanted = _clean(text)
    found = [
        (entry, bullet)
        for section in ("experience", "projects")
        for entry in draft[section]
        for bullet in entry["bullets"]
        if bullet["text"] == wanted
    ]
    if len(found) != 1:
        raise EditError(f"no single bullet reads {text!r}")
    return found[0]


def apply_edit(draft: dict[str, Any], edit: dict[str, Any], profile: Profile) -> dict[str, Any]:
    """A new draft with one reviewer edit applied; the draft passed in isn't touched."""
    draft = copy.deepcopy(draft)
    kind, new = edit["kind"], _clean(edit["new"])
    if kind == "replace":
        old = _clean(edit["old"])
        hits = [(box, key) for box, key in _text_fields(draft) if old and old in box[key]]
        if len(hits) != 1 or hits[0][0][hits[0][1]].count(old) != 1:
            raise EditError(f"the text to replace isn't in exactly one place: {edit['old']!r}")
        box, key = hits[0]
        box[key] = box[key].replace(old, new)
        if key == "text":
            box["evidence"] = list(dict.fromkeys([*box["evidence"], *edit["evidence"]]))
    elif kind == "add_bullet":
        # Marked, so trimming to one page cuts the drafter's bullets first (decision #50).
        bullet = {"text": new, "evidence": list(edit["evidence"]), "added_by_review": True}
        if edit["where"] in {role.id for role in profile.bank.roles}:
            section = "experience"
        elif edit["where"] in {project.id for project in profile.bank.projects}:
            section = "projects"
        else:
            raise EditError(f"no role or project {edit['where']!r}")
        entry = next((e for e in draft[section] if e["where"] == edit["where"]), None)
        if entry is None:
            entry = {"where": edit["where"], "bullets": []}
            draft[section].append(entry)
        entry["bullets"].append(bullet)
    elif kind == "remove_bullet":
        entry, bullet = _find_bullet(draft, edit["old"])
        entry["bullets"].remove(bullet)
    elif kind == "move_first":
        entry, bullet = _find_bullet(draft, edit["old"])
        entry["bullets"].remove(bullet)
        entry["bullets"].insert(0, bullet)
    elif kind == "add_skill":
        if new.lower() in {skill.lower() for skill in draft["skills"]}:
            raise EditError(f"{new!r} is already listed")
        draft["skills"].append(new)
    else:
        raise EditError(f"unknown edit kind {kind!r}")
    return draft


def keywords_in_bullets(
    draft: dict[str, Any], brief: dict[str, Any], fit: dict[str, Any]
) -> set[str]:
    """The job's covered must-haves that some bullet says, by name or in the posting's words."""
    text = "\n".join(bullet["text"] for _, _, bullet in draft_bullets(draft))
    items = {item["skill"]: item for item in brief["must_haves"]}
    said = set()
    for match in fit["covered"]:
        phrases = items.get(match["asked"], {}).get("exact_phrases", [])
        forms = [match["asked"], match["skill"], *phrases]
        if any(mentions(text, form) for form in forms if form):
            said.add(match["asked"])
    return said


def trim_one_bullet(
    draft: dict[str, Any],
    brief: dict[str, Any] | None = None,
    fit: dict[str, Any] | None = None,
) -> str | None:
    """Cut one bullet, keeping one per role or project. None when nothing can go.

    With the job's brief and fit (decision #50): cut the bullet whose loss takes the fewest of the
    job's covered must-haves out of the bullets (the Skills line names them all anyway; a bullet
    gives the keyword its context), so a bullet that alone says a keyword stays. On a tie the
    drafter's bullets go before one the reviewer added, then the last bullet of the role or
    project with the most (bullets are ordered by relevance); calls without a job use only that."""
    entries = [e for s in ("experience", "projects") for e in draft[s] if len(e["bullets"]) > 1]
    if not entries:
        return None
    if brief is None or fit is None:
        return max(entries, key=lambda e: len(e["bullets"]))["bullets"].pop()["text"]

    said_now = keywords_in_bullets(draft, brief, fit)

    def lost(entry: dict[str, Any], index: int) -> int:
        bullet = entry["bullets"].pop(index)
        said = keywords_in_bullets(draft, brief, fit)
        entry["bullets"].insert(index, bullet)
        return len(said_now - said)

    candidates = [
        (
            lost(entry, i),
            bool(entry["bullets"][i].get("added_by_review")),  # the reviewer added it on purpose
            -len(entry["bullets"]),
            -i,
            n,
            i,
        )
        for n, entry in enumerate(entries)
        for i in range(len(entry["bullets"]))
    ]
    *_, n, i = min(candidates)
    return entries[n]["bullets"].pop(i)["text"]


def candidate_data(profile: Profile) -> dict[str, Any]:
    """What the LLMs may know about the candidate. Interview stories stay out: their details
    aren't approved for the page."""
    bank = profile.bank
    return {
        "roles": [
            {"id": r.id, "title": r.title, "employer": r.employer, "start": r.start, "end": r.end}
            for r in bank.roles
        ],
        "projects": [
            {"id": p.id, "name": p.name, "status": p.status, "description": p.description}
            for p in bank.projects
        ],
        "evidence": [
            {
                "id": e.id,
                "where": e.where,
                "summary": e.summary,
                "skills": list(e.skills),
                "level": e.level,
                "metrics": list(e.metrics),
            }
            for e in bank.evidence
        ],
        "skills": [{"name": s.name, "aliases": list(s.aliases)} for s in bank.skills],
    }


def _job_data(job: Job) -> dict[str, Any]:
    keys = (
        "company",
        "title",
        "archetype",
        "seniority",
        "must_haves",
        "nice_to_haves",
        "hidden_signals",
    )
    return {key: job.brief.get(key) for key in keys}


def _fit_data(job: Job) -> dict[str, Any]:
    keys = ("not_covered", "nice_missing", "lead_with")
    covered = {
        key: [{"asked": m["asked"], "skill": m["skill"], "level": m["level"]} for m in job.fit[key]]
        for key in ("covered", "nice_covered")
    }
    return {**covered, **{key: job.fit[key] for key in keys}}


def _dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1)


def drafter_input(job: Job, profile: Profile) -> str:
    """The brief, not the posting: the drafter never reads the posting's own text."""
    return _dumps(
        {
            "job": _job_data(job),
            "fit": _fit_data(job),
            "candidate": candidate_data(profile),
        }
    )


def reviewer_input(
    job: Job,
    profile: Profile,
    draft: dict[str, Any],
    problems: list[str],
    rejected: list[dict[str, Any]],
) -> str:
    shown = {key: draft[key] for key in ("headline", "summary", "experience", "projects", "skills")}
    return _dumps(
        {
            "posting": job.text,
            "job": _job_data(job),
            "fit": _fit_data(job),
            "candidate": candidate_data(profile),
            "draft": shown,
            "code_problems": problems,
            "rejected_edits": rejected,
        }
    )


@dataclass
class Tailored:
    job: Job
    draft: dict[str, Any]
    resume: str
    problems: Problems
    report: PdfReport
    pdf: Path
    history: list[dict[str, Any]] = field(default_factory=list)
    changes: list[dict[str, str]] = field(default_factory=list)
    cost_usd: float = 0.0  # what the LLM calls behind this resume cost
    paid_now_usd: float = 0.0  # the part paid in this run; cached answers are free
    llm_calls: int = 0

    @property
    def status(self) -> str:
        clean = not self.problems.all and self.report.ok and self.report.pages == 1
        return "ready" if clean else "needs_review"

    @property
    def all_problems(self) -> list[str]:
        return [*self.problems.all, *self.report.failures]


def _check(
    draft: dict[str, Any], job: Job, profile: Profile, vocab: Vocabulary
) -> tuple[str, Problems]:
    resume = build_resume(draft, profile)
    problems = check_draft(draft, resume, profile, job.brief, job.fit, vocab)
    try:
        parse_resume(resume)
    except ResumeFormatError as exc:
        problems = Problems((*problems.facts, f"resume format: {exc}"), problems.quality)
    return resume, problems


@dataclass
class Spend:
    total_usd: float = 0.0  # what the calls behind this resume cost, whenever they were made
    paid_now_usd: float = 0.0  # the part paid in this run; cached answers are free
    calls: int = 0

    def add(self, result: LlmResult) -> None:
        cost = result.cost_usd or 0.0
        self.total_usd += cost
        self.paid_now_usd += 0.0 if result.cached else cost
        self.calls += 1


def _ask(
    conn: psycopg.Connection,
    client: LlmClient,
    skill: Skill,
    schema: dict[str, Any],
    data: str,
    settings: LlmSettings,
    spend: Spend,
) -> dict[str, Any]:
    result = ask(conn, client, build_request(skill, schema, data, settings))
    spend.add(result)
    return result.output


def review_rounds(
    conn: psycopg.Connection,
    client: LlmClient,
    job: Job,
    profile: Profile,
    draft: dict[str, Any],
    vocab: Vocabulary,
    settings: LlmSettings,
    skill: Skill,
    spend: Spend,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Up to MAX_REVIEW_ROUNDS reviews. A second round only runs when the checks still report
    problems or an edit was refused."""
    history: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for number in range(1, MAX_REVIEW_ROUNDS + 1):
        _, problems = _check(draft, job, profile, vocab)
        data = reviewer_input(job, profile, draft, problems.all, rejected)
        review = _ask(conn, client, skill, REVIEW_SCHEMA, data, settings, spend)
        applied, rejected = [], []
        for edit in review["edits"]:
            try:
                changed = apply_edit(draft, edit, profile)
            except EditError as exc:
                rejected.append({**edit, "refused_because": str(exc)})
                continue
            before = set(problems.facts)
            _, after = _check(changed, job, profile, vocab)
            broken = sorted(set(after.facts) - before)
            if broken:
                rejected.append({**edit, "refused_because": "; ".join(broken)})
                continue
            draft, problems = changed, after
            applied.append(edit)
        history.append(
            {
                "round": number,
                "verdict": review["verdict"],
                "seven_second_answer": review["seven_second_answer"],
                "applied": applied,
                "rejected": rejected,
                "notes": review["notes"],
            }
        )
        if not problems.all and not rejected:
            break
    return draft, history


def render_and_trim(
    draft: dict[str, Any],
    job: Job,
    profile: Profile,
    vocab: Vocabulary,
    pdf: Path,
    history: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, Problems, PdfReport]:
    """Render; while the page overflows, cut the least relevant bullet. Each cut is recorded."""
    pdf.parent.mkdir(parents=True, exist_ok=True)
    trims = []
    for _ in range(MAX_TRIMS):
        resume, problems = _check(draft, job, profile, vocab)
        doc = parse_resume(resume)
        pdf.write_bytes(render_pdf(doc))
        report = check_pdf(pdf, expected_lines=doc.lines())
        if report.pages <= 1:
            break
        removed = trim_one_bullet(draft, job.brief, job.fit)
        if removed is None:
            break
        trims.append(removed)
    if trims:
        history.append({"trimmed_to_fit_one_page": trims})
    return draft, resume, problems, report


def _slug(text: str, limit: int) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:limit].strip("_")


def job_folder(job: Job, out: Path) -> Path:
    name = f"{job.posting_version_id}_{_slug(job.brief['company'], 20)}"
    return out / f"{name}_{_slug(job.brief['title'], 30)}"


def pdf_name(profile: Profile, job: Job) -> str:
    """FirstLast_DataEngineer_Company.pdf, as resume-tailoring and hiring systems expect."""
    person = re.sub(r"[^A-Za-z0-9]", "", profile.applicant["contact"]["name"]) or "Resume"
    role = (
        "AnalyticsEngineer"
        if job.brief.get("archetype") == "analytics_engineer"
        else ("DataEngineer")
    )
    return f"{person}_{role}_{_slug(job.brief['company'], 30).replace('_', '')}.pdf"


def tailor_job(
    conn: psycopg.Connection,
    client: LlmClient,
    job: Job,
    profile: Profile,
    vocab: Vocabulary,
    settings: LlmSettings,
    drafter: Skill,
    reviewer: Skill,
    out: Path = OUT_DIR,
) -> Tailored:
    spend = Spend()
    output = _ask(conn, client, drafter, DRAFT_SCHEMA, drafter_input(job, profile), settings, spend)
    draft = clean_draft(output)
    draft, history = review_rounds(
        conn, client, job, profile, draft, vocab, settings, reviewer, spend
    )
    pdf = job_folder(job, out) / pdf_name(profile, job)
    draft, resume, problems, report = render_and_trim(draft, job, profile, vocab, pdf, history)
    return Tailored(
        job=job,
        draft=draft,
        resume=resume,
        problems=problems,
        report=report,
        pdf=pdf,
        history=history,
        changes=draft.get("changes", []),
        cost_usd=spend.total_usd,
        paid_now_usd=spend.paid_now_usd,
        llm_calls=spend.calls,
    )


def store(
    conn: psycopg.Connection,
    tailored: Tailored,
    fingerprint: str,
    settings: LlmSettings,
    drafter: Skill,
    reviewer: Skill,
) -> None:
    conn.execute(
        """
        insert into agents.tailored_resumes (
            posting_version_id, profile_fingerprint, tailor_prompt_version,
            reviewer_prompt_version, model, status, review_rounds, draft, resume_md, problems,
            history, pdf_path, cost_usd)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (posting_version_id, profile_fingerprint, tailor_prompt_version,
                     reviewer_prompt_version, model)
        do update set status = excluded.status, review_rounds = excluded.review_rounds,
            draft = excluded.draft, resume_md = excluded.resume_md, problems = excluded.problems,
            history = excluded.history, pdf_path = excluded.pdf_path, cost_usd = excluded.cost_usd
        """,
        (
            tailored.job.posting_version_id,
            fingerprint,
            drafter.prompt_version,
            reviewer.prompt_version,
            settings.model,
            tailored.status,
            sum("round" in entry for entry in tailored.history),
            json.dumps(tailored.draft, ensure_ascii=False),
            tailored.resume,
            json.dumps(tailored.all_problems, ensure_ascii=False),
            json.dumps(tailored.history, ensure_ascii=False),
            str(tailored.pdf),
            tailored.cost_usd,
        ),
    )


def scored_jobs(
    conn: psycopg.Connection,
    profile: Profile,
    rules: Rules,
    vocab: Vocabulary,
    settings: LlmSettings,
    today: date,
) -> list[Job]:
    """Every current brief with its score, best first."""
    prompt_version = load_skill("jd-analysis").prompt_version
    jobs = [
        Job(
            posting_version_id,
            brief,
            text,
            score_brief(brief, profile, rules, vocab, today, text).as_json(),
        )
        for posting_version_id, brief, text in load_briefs(conn, prompt_version)
    ]
    return sorted(jobs, key=lambda job: (-job.fit["score"], job.posting_version_id))


def choose_jobs(jobs: list[Job], ids: list[int], top: int | None) -> tuple[list[Job], list[str]]:
    """The jobs to tailor, and why any asked for can't be. A job scored skip is never tailored."""
    if not ids:
        return [job for job in jobs if job.fit["decision"] != "skip"][: top or 0], []
    by_id = {job.posting_version_id: job for job in jobs}
    chosen, refused = [], []
    for posting_version_id in ids:
        job = by_id.get(posting_version_id)
        if job is None:
            refused.append(f"#{posting_version_id}: no current brief")
        elif job.fit["decision"] == "skip":
            refused.append(f"#{posting_version_id}: scored skip ({job.fit['dealbreakers']})")
        else:
            chosen.append(job)
    return chosen, refused


def _skill_from(path: Path | None, name: str) -> Skill:
    """A proposed prompt from its file, or the adopted one."""
    if path is None:
        return load_skill(name)
    return parse_skill(path.read_text(encoding="utf-8"), str(path))


def main(argv: list[str] | None = None) -> int:
    from agents.tailor_review import write_index, write_job_files
    from pipeline.db import connect, migrate

    parser = argparse.ArgumentParser(prog="python -m agents.tailor")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="tailor resumes for jobs worth applying to")
    run_cmd.add_argument("ids", nargs="*", type=int, help="posting version ids")
    run_cmd.add_argument("--top", type=int, help="the best scored jobs, instead of ids")
    run_cmd.add_argument("--dry-run", action="store_true", help="list the jobs; no calls")
    run_cmd.add_argument("--out", type=Path)
    trial = run_cmd.add_argument_group("try proposals on real jobs; nothing is stored")
    trial.add_argument("--drafter-skill", type=Path, help="a proposed resume-tailoring prompt")
    trial.add_argument("--reviewer-skill", type=Path, help="a proposed resume-reviewer prompt")
    trial.add_argument("--jd-proposal", type=Path, help="a proposed jd-analysis prompt (needs ids)")
    trial.add_argument("--vocabulary", type=Path, help="a proposed skill vocabulary")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if bool(args.ids) == bool(args.top):
        parser.error("give posting version ids or --top N, not both")
    if args.jd_proposal and not args.ids:
        parser.error("--jd-proposal needs posting version ids")
    is_trial = any((args.drafter_skill, args.reviewer_skill, args.jd_proposal, args.vocabulary))
    out = args.out or (TRIAL_DIR if is_trial else OUT_DIR)

    settings = llm_settings()
    folder = profile_dir()
    profile, rules = load_profile(folder), load_rules()
    vocab = load_vocabulary(args.vocabulary) if args.vocabulary else load_vocabulary()
    drafter = _skill_from(args.drafter_skill, "resume-tailoring")
    reviewer = _skill_from(args.reviewer_skill, "resume-reviewer")
    with connect() as conn:
        migrate(conn)
        if args.jd_proposal:
            proposal = _skill_from(args.jd_proposal, "jd-analysis")
            briefs, _ = brief_postings(conn, AnthropicClient(), settings, proposal, args.ids)
            jobs = [
                Job(i, brief, text, score_brief(
                    brief, profile, rules, vocab, date.today(), text).as_json())
                for i, (brief, text) in briefs.items()
            ]
        else:
            jobs = scored_jobs(conn, profile, rules, vocab, settings, date.today())
        chosen, refused = choose_jobs(jobs, args.ids, args.top)
        for reason in refused:
            print(f"REFUSED {reason}")
        if args.dry_run:
            for job in chosen:
                print(
                    f"#{job.posting_version_id} {job.fit['score']:3d} {job.brief['company']} | "
                    f"{job.brief['title']}"
                )
            print(f"about ${ESTIMATED_USD_PER_RESUME * len(chosen):.2f}; nothing was called")
            return 0
        client = AnthropicClient()
        results: list[Tailored] = []
        failed = 0
        for job in chosen:
            label = f"#{job.posting_version_id} {job.brief['company']} | {job.brief['title']}"
            try:
                tailored = tailor_job(
                    conn, client, job, profile, vocab, settings, drafter, reviewer, out
                )
            except (LlmError, ResumeFormatError) as exc:
                print(f"FAILED {label}: {exc}")
                failed += 1
                continue
            if not is_trial:
                store(conn, tailored, profile_fingerprint(folder), settings, drafter, reviewer)
            page = write_job_files(tailored, out)
            results.append(tailored)
            print(
                f"{tailored.status:12} {label}: {tailored.llm_calls} calls, "
                f"${tailored.cost_usd:.3f}, text to {tailored.report.fill:.0%} of the page"
            )
            for problem in tailored.all_problems:
                print(f"    {problem}")
            print(f"    {page}")
        if results:
            print(f"index: {write_index(results, out)}")
        print(f"paid in this run: ${sum(t.paid_now_usd for t in results):.2f}")
    return 1 if failed or refused else 0


if __name__ == "__main__":
    sys.exit(main())
