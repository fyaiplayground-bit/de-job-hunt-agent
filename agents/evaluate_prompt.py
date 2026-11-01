"""Evaluate a jd-analysis prompt against the golden set before it is adopted (decision #32).

    uv run python -m agents.evaluate_prompt                                  # current prompt only
    uv run python -m agents.evaluate_prompt config/proposals/jd-analysis.v3.md
    uv run python -m agents.evaluate_prompt PROPOSAL --effort low            # proposal at low

The current prompt (at LLM_EFFORT) and the proposal (at --effort, default the same) brief every
golden case with the same model; the report compares must-have recall and precision, archetype,
work mode and years. Answers are cached (decision #30): re-running costs nothing, only a new
prompt or effort makes calls. Nothing is written to agents.jd_briefs. Same loop as the triage
rules (#22): propose, evaluate, FL approves, copy into .claude/skills, bump, lock, record.
"""

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import psycopg

from agents.jd_analysis import BRIEF_SCHEMA, Candidate, _display_fields
from agents.llm import AnthropicClient, LlmClient, LlmError, ask, build_request
from agents.skills import Skill, load_skill, parse_skill
from pipeline.config import LLM_EFFORTS, REPO_ROOT, LlmSettings, llm_settings
from pipeline.safety_gate import GATE_VERSION

GOLDEN_FILE = REPO_ROOT / "tests" / "fixtures" / "jd_golden.toml"
MUST_HAVE_TOLERANCE = 1  # a proposal may find one fewer labeled must-have in total (LLM noise)


@dataclass(frozen=True)
class GoldenCase:
    name: str
    source: str
    source_job_id: str
    content_hash: str
    why: str
    must_haves: tuple[tuple[str, ...], ...]  # each entry: accepted names for one skill
    archetype: tuple[str, ...]  # () = not scored
    work_mode: str
    years_required: tuple[int, ...]  # () = must be null


def load_golden(path: Path = GOLDEN_FILE) -> list[GoldenCase]:
    cases = []
    for raw in tomllib.loads(path.read_text(encoding="utf-8"))["case"]:
        cases.append(GoldenCase(
            name=raw["name"], source=raw["source"], source_job_id=raw["source_job_id"],
            content_hash=raw["content_hash"], why=raw["why"],
            must_haves=tuple(tuple(a.strip() for a in m.split("|")) for m in raw["must_haves"]),
            archetype=tuple(raw["archetype"]), work_mode=raw["work_mode"],
            years_required=tuple(raw["years_required"]),
        ))
    return cases


def normalize(text: str) -> str:
    """Lowercase, punctuation to spaces (keeping + and #), single spaces: "CI/CD" -> "ci cd"."""
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", text.lower()).split())


def _names(item: dict[str, Any]) -> set[str]:
    return {normalize(item["skill"]), *(normalize(p) for p in item["exact_phrases"])}


@dataclass(frozen=True)
class CaseScore:
    name: str
    expected: int
    hits: int
    predicted: int
    matched_predicted: int
    missed: tuple[str, ...]
    misplaced: tuple[str, ...]  # missed as a must-have but listed as a nice-to-have
    archetype_ok: bool | None  # None = not scored
    work_mode_ok: bool
    years_ok: bool
    years_got: int | None
    error: str | None = None


def score_case(case: GoldenCase, brief: dict[str, Any]) -> CaseScore:
    must, nice = brief["must_haves"], brief["nice_to_haves"]
    hits, matched, missed, misplaced = 0, set(), [], []
    for alternatives in case.must_haves:
        accepted = {normalize(a) for a in alternatives}
        found = {i for i, item in enumerate(must) if _names(item) & accepted}
        if found:
            hits += 1
            matched |= found
        else:
            missed.append(alternatives[0])
            if any(_names(item) & accepted for item in nice):
                misplaced.append(alternatives[0])
    years = brief["years_required"]
    return CaseScore(
        name=case.name, expected=len(case.must_haves), hits=hits, predicted=len(must),
        matched_predicted=len(matched), missed=tuple(missed), misplaced=tuple(misplaced),
        archetype_ok=None if not case.archetype else brief["archetype"] in case.archetype,
        work_mode_ok=brief["work_mode"] == case.work_mode,
        years_ok=years is None if not case.years_required else years in case.years_required,
        years_got=years,
    )


def failed_case(case: GoldenCase, error: str) -> CaseScore:
    return CaseScore(
        name=case.name, expected=len(case.must_haves), hits=0, predicted=0, matched_predicted=0,
        missed=tuple(m[0] for m in case.must_haves), misplaced=(), archetype_ok=False,
        work_mode_ok=False, years_ok=False, years_got=None, error=error,
    )


@dataclass
class Totals:
    hits: int = 0
    expected: int = 0
    matched_predicted: int = 0
    predicted: int = 0
    archetype_ok: int = 0
    archetype_scored: int = 0
    work_mode_ok: int = 0
    years_ok: int = 0
    cases: int = 0
    failed: int = 0

    @classmethod
    def of(cls, scores: list[CaseScore]) -> "Totals":
        t = cls()
        for s in scores:
            t.cases += 1
            t.failed += s.error is not None
            t.hits += s.hits
            t.expected += s.expected
            t.matched_predicted += s.matched_predicted
            t.predicted += s.predicted
            if s.archetype_ok is not None:
                t.archetype_scored += 1
                t.archetype_ok += s.archetype_ok
            t.work_mode_ok += s.work_mode_ok
            t.years_ok += s.years_ok
        return t


def compare(current: Totals, proposed: Totals) -> list[str]:
    """Why the proposal is worse than the current prompt; [] means it may be adopted."""
    problems = []
    if proposed.hits < current.hits - MUST_HAVE_TOLERANCE:
        problems.append(f"must-haves found {proposed.hits} < {current.hits} (tolerance 1)")
    for label, attr in (("archetype", "archetype_ok"), ("work mode", "work_mode_ok"),
                        ("years", "years_ok")):
        if getattr(proposed, attr) < getattr(current, attr):
            problems.append(
                f"{label} right {getattr(proposed, attr)} < {getattr(current, attr)}"
            )
    if proposed.failed > current.failed:
        problems.append(f"{proposed.failed} cases failed (current: {current.failed})")
    return problems


def resolve(conn: psycopg.Connection, case: GoldenCase) -> Candidate | None:
    """The golden posting from the local database, or None when this database doesn't have it."""
    row = conn.execute(
        "select p.posting_version_id, p.company,"
        " coalesce(p.payload->>'title', p.payload->>'text', ''), p.payload, g.cleaned_text"
        " from raw.job_postings p join gate.results g"
        "   on g.posting_version_id = p.posting_version_id and g.gate_version = %s"
        " where p.source = %s and p.source_job_id = %s and p.content_hash = %s",
        (GATE_VERSION, case.source, case.source_job_id, case.content_hash),
    ).fetchone()
    if row is None:
        return None
    posting_version_id, company, title, payload, cleaned_text = row
    name, location, url = _display_fields(case.source, company, payload)
    return Candidate(posting_version_id, case.source, name, title, location, url, cleaned_text)


@dataclass
class Evaluation:
    label: str
    scores: list[CaseScore] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    cost_usd: float = 0.0

    @property
    def totals(self) -> Totals:
        return Totals.of(self.scores)


def evaluate(
    conn: psycopg.Connection,
    client: LlmClient,
    settings: LlmSettings,
    skill: Skill,
    cases: list[GoldenCase],
) -> Evaluation:
    result = Evaluation(label=f"{skill.prompt_version} · {settings.model} · {settings.effort}")
    for case in cases:
        candidate = resolve(conn, case)
        if candidate is None:
            result.missing.append(case.name)
            continue
        request = build_request(skill, BRIEF_SCHEMA, candidate.data(), settings)
        try:
            answer = ask(conn, client, request)
        except LlmError as exc:
            result.scores.append(failed_case(case, str(exc)))
            continue
        if not answer.cached:
            result.cost_usd += answer.cost_usd or 0.0
        result.scores.append(score_case(case, answer.output))
    return result


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole}" + (f" ({100 * part / whole:.0f}%)" if whole else "")


def format_evaluation(ev: Evaluation) -> str:
    t = ev.totals
    lines = [f"## {ev.label}", ""]
    for s in ev.scores:
        if s.error:
            lines.append(f"- {s.name}: FAILED {s.error}")
            continue
        flags = []
        if s.archetype_ok is False:
            flags.append("archetype wrong")
        if not s.work_mode_ok:
            flags.append("work mode wrong")
        if not s.years_ok:
            flags.append(f"years {s.years_got}")
        if s.missed:
            flags.append("missed " + ", ".join(s.missed))
        if s.misplaced:
            flags.append("as nice-to-have: " + ", ".join(s.misplaced))
        lines.append(
            f"- {s.name}: must-haves {s.hits}/{s.expected}, listed {s.predicted}"
            + (f" · {'; '.join(flags)}" if flags else " · all right")
        )
    lines += [
        "",
        f"must-haves found: {_pct(t.hits, t.expected)}",
        f"listed must-haves that are labeled: {_pct(t.matched_predicted, t.predicted)}"
        " (labels hold the main must-haves only, so this is for comparison, not a score)",
        f"archetype right: {_pct(t.archetype_ok, t.archetype_scored)}",
        f"work mode right: {_pct(t.work_mode_ok, t.cases)}",
        f"years right: {_pct(t.years_ok, t.cases)}",
        f"new calls cost: ${ev.cost_usd:.2f}",
    ]
    if ev.missing:
        lines.append(f"not in this database (skipped): {', '.join(ev.missing)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.evaluate_prompt")
    parser.add_argument("proposal", nargs="?", help="a proposed jd-analysis SKILL.md")
    parser.add_argument("--effort", choices=LLM_EFFORTS, help="effort for the proposal")
    args = parser.parse_args(argv)

    from pipeline.db import connect, migrate

    settings = llm_settings()
    current = load_skill("jd-analysis")
    cases = load_golden()
    client = AnthropicClient()
    with connect() as conn:
        migrate(conn)
        base = evaluate(conn, client, settings, current, cases)
        print(format_evaluation(base))
        if not args.proposal:
            return 0
        path = Path(args.proposal)
        proposed = parse_skill(path.read_text(encoding="utf-8"), str(path))
        if proposed.name != current.name or proposed.version < current.version:
            print(f"FAIL {path} should be {current.name} at version >= {current.version}")
            return 1
        proposed_settings = replace(settings, effort=args.effort or settings.effort)
        candidate = evaluate(conn, client, proposed_settings, proposed, cases)
        print()
        print(format_evaluation(candidate))
        problems = compare(base.totals, candidate.totals)
        print()
        print("VERDICT: " + ("FAIL\n  - " + "\n  - ".join(problems) if problems else "PASS"))
        return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
