"""fit-scoring (Agent 2, decision #35): score each job brief against the candidate profile.

    uv run python -m agents.fit_scoring run              # score every current brief (free, fast)
    uv run python -m agents.fit_scoring top --n 20       # the best matches so far
    uv run python -m agents.fit_scoring show 12345       # why one posting got its score
    uv run python -m agents.fit_scoring unmatched        # JD skill names the vocabulary misses

Pure code, no LLM: the same brief, profile and rules always give the same score. Skills are
matched by name, alias (the Evidence Bank), synonym or skill family (config/skill_vocabulary
.toml); the score, decision and dealbreakers follow config/fit_scoring.toml. Scores are stored
in agents.fit_scores per profile fingerprint and rules version, so a new profile or a rules
change is a full rescore in seconds.
"""

import argparse
import hashlib
import json
import re
import sys
import tomllib
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from agents.profile import (
    APPLICANT_PROFILE_FILE,
    EVIDENCE_BANK_FILE,
    LEVELS,
    RESUME_FILE,
    EvidenceBank,
    Profile,
    load_profile,
)
from agents.skills import load_skill
from pipeline.config import REPO_ROOT, llm_settings, profile_dir
from pipeline.safety_gate import GATE_VERSION

RULES_FILE = REPO_ROOT / "config" / "fit_scoring.toml"
VOCABULARY_FILE = REPO_ROOT / "config" / "skill_vocabulary.toml"
# A brief's skill name may bundle alternatives: "Cloud SQL / PostgreSQL", "AWS (S3, Glue)".
NAME_SEPARATORS = re.compile(r"\s+/\s+|\s+or\s+|\s+and\s+|\s*&\s*|[(),]")


@dataclass(frozen=True)
class ClearanceRules:
    ignore: tuple[re.Pattern[str], ...]
    obtain: tuple[re.Pattern[str], ...]
    hold: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class Rules:
    version: int
    must_weight: float
    nice_weight: float
    core_weight: float
    archetype_adjustment: dict[str, float]
    apply_bar: float
    referral_score: float
    years_tolerance: float
    location_check: str
    salary_floor_check: bool
    sponsorship_check: bool
    clearance: ClearanceRules | None = None


def _load_clearance(section: dict[str, list[str]] | None) -> ClearanceRules | None:
    if section is None:
        return None

    def compiled(key: str) -> tuple[re.Pattern[str], ...]:
        return tuple(re.compile(pattern, re.IGNORECASE) for pattern in section[key])

    return ClearanceRules(compiled("ignore"), compiled("obtain"), compiled("hold"))


def load_rules(path: Path = RULES_FILE) -> Rules:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = Rules(
        version=int(data["version"]),
        must_weight=float(data["must_weight"]),
        nice_weight=float(data["nice_weight"]),
        core_weight=float(data["core_weight"]),
        archetype_adjustment={k: float(v) for k, v in data["archetype_adjustment"].items()},
        apply_bar=float(data["decision"]["apply_bar"]),
        referral_score=float(data["decision"]["referral_score"]),
        years_tolerance=float(data["dealbreakers"]["years_tolerance"]),
        location_check=data["dealbreakers"]["location_check"],
        salary_floor_check=bool(data["dealbreakers"]["salary_floor_check"]),
        sponsorship_check=bool(data["dealbreakers"]["sponsorship_check"]),
        clearance=_load_clearance(data["dealbreakers"].get("clearance")),
    )
    if rules.location_check != "off":
        raise ValueError("location_check: only 'off' exists so far (the state check comes in M5)")
    return rules


@dataclass(frozen=True)
class Vocabulary:
    version: int
    synonyms: dict[str, str]  # lowercased wording -> canonical name
    families: dict[str, tuple[str, ...]]  # lowercased umbrella -> member names


def load_vocabulary(path: Path = VOCABULARY_FILE) -> Vocabulary:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Vocabulary(
        version=int(data["version"]),
        synonyms={k.strip().lower(): v for k, v in data.get("synonyms", {}).items()},
        families={k.strip().lower(): tuple(v) for k, v in data.get("families", {}).items()},
    )


def profile_fingerprint(folder: Path) -> str:
    """SHA-256 over the three profile files (line endings normalized): any edit, a new score."""
    digest = hashlib.sha256()
    for name in (EVIDENCE_BANK_FILE, APPLICANT_PROFILE_FILE, RESUME_FILE):
        digest.update((folder / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode())
    return digest.hexdigest()


def candidate_years(bank: EvidenceBank, today: date) -> float:
    """Years across all roles (analyst and BIE alike, FL 2026-11-02), months counted inclusive."""
    months = 0
    for role in bank.roles:
        start_year, start_month = (int(x) for x in role.start.split("-"))
        if role.end:
            end_year, end_month = (int(x) for x in role.end.split("-"))
        else:
            end_year, end_month = today.year, today.month
        months += (end_year - start_year) * 12 + end_month - start_month + 1
    return round(months / 12, 1)


@dataclass(frozen=True)
class SkillMatch:
    asked: str  # the brief's skill name
    skill: str | None  # the profile skill that covers it; None = not covered
    level: str | None
    evidence: tuple[str, ...] = ()
    via: str = ""  # name / alias / synonym / family


def _split(raw: str) -> list[str]:
    parts = [raw.strip(), *(p.strip() for p in NAME_SEPARATORS.split(raw))]
    return list(dict.fromkeys(p for p in parts if p))


def _strongest(bank: EvidenceBank, skills: list[str]) -> str | None:
    levels = {bank.skill_level(s) for s in skills}
    return next((level for level in LEVELS if level in levels), None)


def _resolve(
    name: str, bank: EvidenceBank, vocab: Vocabulary, families: bool = True, depth: int = 0
) -> tuple[list[str], str]:
    """Profile skills that cover `name`, and how: name, alias, synonym or family."""
    if depth > 3:
        return [], ""
    found = bank.find_skill(name)
    if found:
        return [found.name], "name" if found.name.lower() == name.lower() else "alias"
    key = name.lower()
    if key in vocab.synonyms:
        skills, how = _resolve(vocab.synonyms[key], bank, vocab, families, depth + 1)
        return skills, "family" if how == "family" else "synonym" if skills else ""
    if families and key in vocab.families:
        hits: list[str] = []
        for member in vocab.families[key]:
            hits += _resolve(member, bank, vocab, families, depth + 1)[0]
        return list(dict.fromkeys(hits)), "family"
    return [], ""


def match_skill(item: dict[str, Any], bank: EvidenceBank, vocab: Vocabulary) -> SkillMatch:
    """The brief's skill name (and its parts) may match through any route. The posting's exact
    phrases only match a profile skill directly or by synonym, never through a family: a phrase
    like "cloud data warehouse" quoted next to Snowflake must not make Redshift cover Snowflake."""
    candidates = [(name, True) for name in _split(item["skill"])]
    candidates += [(p, False) for raw in item.get("exact_phrases", []) for p in _split(raw)]
    for name, families in candidates:
        skills, how = _resolve(name, bank, vocab, families)
        if not skills:
            continue
        best = _strongest(bank, skills)
        best_skill = next(s for s in skills if bank.skill_level(s) == best)
        evidence = tuple(e.id for e in bank.evidence_for(best_skill))
        return SkillMatch(item["skill"], best_skill, best, evidence, how)
    return SkillMatch(item["skill"], None, None)


@dataclass
class FitResult:
    score: int
    decision: str  # apply_referral / apply / skip
    must_have_coverage: float | None
    nice_coverage: float | None
    covered: list[SkillMatch] = field(default_factory=list)
    not_covered: list[str] = field(default_factory=list)
    nice_covered: list[SkillMatch] = field(default_factory=list)
    nice_missing: list[str] = field(default_factory=list)
    dealbreakers: list[str] = field(default_factory=list)
    lead_with: list[str] = field(default_factory=list)
    candidate_years: float = 0.0
    work_mode: str = ""
    location: str = ""

    def as_json(self) -> dict[str, Any]:
        def matches(items: list[SkillMatch]) -> list[dict[str, Any]]:
            return [
                {"asked": m.asked, "skill": m.skill, "level": m.level,
                 "evidence": list(m.evidence), "via": m.via}
                for m in items
            ]

        return {
            "score": self.score, "decision": self.decision,
            "must_have_coverage": self.must_have_coverage, "nice_coverage": self.nice_coverage,
            "covered": matches(self.covered), "not_covered": self.not_covered,
            "nice_covered": matches(self.nice_covered), "nice_missing": self.nice_missing,
            "dealbreakers": self.dealbreakers, "lead_with": self.lead_with,
            "candidate_years": self.candidate_years, "work_mode": self.work_mode,
            "location": self.location,
        }


def find_clearance(text: str, rules: ClearanceRules) -> tuple[str, str] | None:
    """What the text asks about a security clearance: ("hold" or "obtain", the words that say so).
    None = it asks for none. A posting that asks for both counts as "hold"."""
    for pattern in rules.ignore:
        text = pattern.sub(" ", text)
    obtain = next((m[0] for p in rules.obtain if (m := p.search(text))), None)
    for pattern in rules.obtain:
        text = pattern.sub(" ", text)
    hold = next((m[0] for p in rules.hold if (m := p.search(text))), None)
    if hold:
        return "hold", " ".join(hold.split())
    return ("obtain", " ".join(obtain.split())) if obtain else None


def _clearance_dealbreaker(
    brief: dict[str, Any], posting_text: str, applicant: dict[str, Any], rules: ClearanceRules
) -> str | None:
    hit = find_clearance(f"{brief.get('title', '')}\n{posting_text}", rules)
    background = applicant["background"]
    if hit is None or background["has_security_clearance"]:
        return None
    tier, words = hit
    if tier == "obtain" and background["can_obtain_security_clearance"]:
        return None
    return f"clearance: the posting asks for one the profile doesn't have ({words!r})"


def _dealbreakers(
    brief: dict[str, Any],
    applicant: dict[str, Any],
    years: float,
    rules: Rules,
    posting_text: str = "",
) -> list[str]:
    found = []
    if rules.clearance:
        clearance = _clearance_dealbreaker(brief, posting_text, applicant, rules.clearance)
        if clearance:
            found.append(clearance)
    asked = brief.get("years_required")
    if isinstance(asked, int | float) and asked > years + rules.years_tolerance:
        found.append(f"years: asks {asked:g}, profile has {years:g}")
    salary = brief.get("salary") or {}
    top = salary.get("max") if salary.get("max") is not None else salary.get("min")
    floor = applicant["compensation"]["base_salary_floor"]
    currency = salary.get("currency")
    if (rules.salary_floor_check and isinstance(top, int | float) and top >= 1000
            and currency in (None, "USD", "$") and top < floor):
        found.append(f"salary: top of range {top:,.0f} is below the floor {floor:,}")
    needs = applicant["work_authorization"]
    if (rules.sponsorship_check and brief.get("sponsorship") == "not_available"
            and (needs["needs_sponsorship_now"] or needs["needs_sponsorship_future"])):
        found.append("sponsorship: the posting won't sponsor and the profile needs it")
    return found


def score_brief(
    brief: dict[str, Any],
    profile: Profile,
    rules: Rules,
    vocab: Vocabulary,
    today: date,
    posting_text: str = "",
) -> FitResult:
    bank = profile.bank
    years = candidate_years(bank, today)
    must = [(item, match_skill(item, bank, vocab)) for item in brief["must_haves"]]
    nice = [match_skill(item, bank, vocab) for item in brief["nice_to_haves"]]

    def weight(item: dict[str, Any]) -> float:
        return rules.core_weight if item.get("weight") == "core" else 1.0

    must_total = sum(weight(item) for item, _ in must)
    must_cov = (
        sum(weight(item) for item, m in must if m.skill) / must_total if must_total else None
    )
    # No nice-to-haves listed: count them as covered as well as the must-haves are, so a short
    # posting is neither rewarded nor punished for what it left out.
    nice_cov = sum(1 for m in nice if m.skill) / len(nice) if nice else must_cov

    result = FitResult(
        score=0, decision="skip", must_have_coverage=must_cov, nice_coverage=nice_cov,
        covered=[m for _, m in must if m.skill],
        not_covered=[m.asked for _, m in must if not m.skill],
        nice_covered=[m for m in nice if m.skill],
        nice_missing=[m.asked for m in nice if not m.skill],
        candidate_years=years, work_mode=brief.get("work_mode", ""),
        location=brief.get("board_location") or ", ".join(brief.get("locations", [])),
    )
    if must_cov is None:
        result.dealbreakers = ["brief lists no must-haves (posting text too thin to judge)"]
        return result
    raw = (rules.must_weight * must_cov + rules.nice_weight * (nice_cov or 0.0)
           + rules.archetype_adjustment.get(brief.get("archetype", ""), 0.0))
    result.score = int(max(0, min(100, round(raw))))
    result.dealbreakers = _dealbreakers(brief, profile.applicant, years, rules, posting_text)
    core_first = sorted(
        ((item, m) for item, m in must if m.skill),
        key=lambda pair: (pair[0].get("weight") != "core", LEVELS.index(pair[1].level)),
    )
    result.lead_with = list(dict.fromkeys(m.skill for _, m in core_first))[:5]
    if result.dealbreakers or must_cov < rules.apply_bar:
        result.decision = "skip"
    elif result.score >= rules.referral_score:
        result.decision = "apply_referral"
    else:
        result.decision = "apply"
    return result


def skip_reason(result: dict[str, Any], rules: Rules) -> str:
    """One short label for why a stored result was skipped (for the daily report)."""
    if result["dealbreakers"]:
        return result["dealbreakers"][0].split(":")[0]
    return "must-have coverage below the bar"


@dataclass
class ScoreRun:
    scored: int = 0
    results: list[tuple[int, dict[str, Any], dict[str, Any]]] = field(default_factory=list)


def load_briefs(
    conn: psycopg.Connection, prompt_version: str, model: str
) -> list[tuple[int, dict[str, Any], str]]:
    """(posting version, brief, the gate's cleaned text) for every brief of this version."""
    return conn.execute(
        "select b.posting_version_id, b.brief, coalesce(g.cleaned_text, '')"
        " from agents.jd_briefs b"
        " left join gate.results g on g.posting_version_id = b.posting_version_id"
        "  and g.gate_version = %s"
        " where b.prompt_version = %s and b.model = %s order by b.posting_version_id",
        (GATE_VERSION, prompt_version, model),
    ).fetchall()


def run(
    conn: psycopg.Connection,
    profile: Profile | None = None,
    rules: Rules | None = None,
    vocab: Vocabulary | None = None,
    only: Collection[int] | None = None,
    today: date | None = None,
    brief_prompt_version: str | None = None,
    brief_model: str | None = None,
) -> ScoreRun:
    """Score every brief of the current jd-analysis prompt version and model (or only the given
    posting versions) and store the results. Recomputing an existing score changes nothing."""
    folder = profile.folder if profile else profile_dir()
    profile = profile or load_profile(folder)
    rules, vocab, today = rules or load_rules(), vocab or load_vocabulary(), today or date.today()
    prompt_version = brief_prompt_version or load_skill("jd-analysis").prompt_version
    model = brief_model or llm_settings().model
    fingerprint = profile_fingerprint(folder)
    rows = load_briefs(conn, prompt_version, model)
    wanted = None if only is None else set(only)
    summary = ScoreRun()
    for posting_version_id, brief, posting_text in rows:
        if wanted is not None and posting_version_id not in wanted:
            continue
        result = score_brief(brief, profile, rules, vocab, today, posting_text).as_json()
        conn.execute(
            "insert into agents.fit_scores (posting_version_id, brief_prompt_version,"
            " brief_model, profile_fingerprint, rules_version, vocabulary_version, score,"
            " decision, result) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict do nothing",
            (posting_version_id, prompt_version, model, fingerprint, rules.version,
             vocab.version, result["score"], result["decision"], json.dumps(result)),
        )
        summary.scored += 1
        summary.results.append((posting_version_id, brief, result))
    return summary


def unmatched_names(conn: psycopg.Connection, limit: int = 30) -> list[tuple[str, int]]:
    """Must-have names in stored scores that matched nothing, most frequent first."""
    rows = conn.execute(
        "select jsonb_array_elements_text(result->'not_covered') from agents.fit_scores"
    ).fetchall()
    return Counter(name for (name,) in rows).most_common(limit)


DECISION_LABEL = {"apply_referral": "apply + referral", "apply": "apply", "skip": "skip"}


def format_result(posting_version_id: int, brief: dict[str, Any], r: dict[str, Any]) -> str:
    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.0f}%"

    lines = [
        f"#{posting_version_id} {brief['company']} | {brief['title']}",
        f"  {DECISION_LABEL[r['decision']]} · score {r['score']} · must-haves "
        f"{pct(r['must_have_coverage'])} · nice-to-haves {pct(r['nice_coverage'])} · "
        f"{r['work_mode']} · {r['location']}",
    ]
    if r["dealbreakers"]:
        lines.append("  dealbreakers: " + "; ".join(r["dealbreakers"]))
    covered = ", ".join(f"{m['asked']} ({m['level']})" for m in r["covered"])
    lines.append(f"  covered: {covered or '-'}")
    lines.append(f"  not covered: {', '.join(r['not_covered']) or '-'}")
    if r["lead_with"]:
        lines.append(f"  lead with: {', '.join(r['lead_with'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.fit_scoring")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="score every current brief")
    top = commands.add_parser("top", help="best matches under the current profile and rules")
    top.add_argument("--n", type=int, default=20)
    show = commands.add_parser("show", help="one posting's score and why")
    show.add_argument("posting_version_id", type=int)
    commands.add_parser("unmatched", help="must-have names the vocabulary doesn't cover")
    args = parser.parse_args(argv)

    from pipeline.db import connect, migrate

    with connect() as conn:
        migrate(conn)
        summary = run(conn)
        if args.command == "run":
            decisions = Counter(r["decision"] for _, _, r in summary.results)
            print(f"scored {summary.scored} briefs: " + ", ".join(
                f"{DECISION_LABEL[d]} {n}" for d, n in decisions.most_common()))
        elif args.command == "top":
            best = sorted(summary.results, key=lambda t: (t[2]["decision"] == "skip",
                                                          -t[2]["score"]))[: args.n]
            for posting_version_id, brief, result in best:
                print(format_result(posting_version_id, brief, result))
        elif args.command == "show":
            matches = [t for t in summary.results if t[0] == args.posting_version_id]
            if not matches:
                print("no current brief for that posting version")
                return 1
            print(format_result(*matches[0]))
        else:
            for name, n in unmatched_names(conn):
                print(f"{n:4}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
