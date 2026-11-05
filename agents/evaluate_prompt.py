"""Evaluate a jd-analysis prompt against the golden set before it is adopted (decision #32).

    uv run python -m agents.evaluate_prompt                                  # current prompt only
    uv run python -m agents.evaluate_prompt config/proposals/jd-analysis.v3.md
    uv run python -m agents.evaluate_prompt PROPOSAL --effort low            # proposal at low
    uv run python -m agents.evaluate_prompt PROPOSAL --review                # + review page

The current prompt (at LLM_EFFORT) and the proposal (at --effort, default the same) brief every
golden case with the same model; the report compares must-haves found, nice-to-haves kept,
nice-to-haves wrongly promoted to must-haves, archetype, work mode and years. Answers are
cached (decision #30): re-running costs nothing, only a new prompt or effort makes calls.
Nothing is written to agents.jd_briefs. --review writes output/golden_review.html (local, not
committed): each posting's text next to its labels and the brief, so a person can check both.
Same loop as the triage rules (#22): propose, evaluate, FL approves, copy into .claude/skills,
bump, lock, record.
"""

import argparse
import html
import re
import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import psycopg

from agents.fit_scoring import _split
from agents.jd_analysis import BRIEF_SCHEMA, Candidate, _display_fields
from agents.llm import AnthropicClient, LlmClient, LlmError, ask, build_request
from agents.skills import Skill, load_skill, parse_skill
from pipeline.config import LLM_EFFORTS, REPO_ROOT, LlmSettings, llm_settings
from pipeline.safety_gate import GATE_VERSION

GOLDEN_FILE = REPO_ROOT / "tests" / "fixtures" / "jd_golden.toml"
REVIEW_PAGE = REPO_ROOT / "output" / "golden_review.html"
TOLERANCE = 1  # a proposal may do one item worse on the skill counts (LLM noise)


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
    nice_to_haves: tuple[tuple[str, ...], ...] = ()
    one_entry: tuple[tuple[tuple[str, ...], ...], ...] = ()  # alternatives kept together
    not_must_haves: tuple[str, ...] = ()  # job functions that aren't skills


def _alternatives(entries: list[str]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(a.strip() for a in entry.split("|")) for entry in entries)


def load_golden(path: Path = GOLDEN_FILE) -> list[GoldenCase]:
    cases = []
    for raw in tomllib.loads(path.read_text(encoding="utf-8"))["case"]:
        cases.append(GoldenCase(
            name=raw["name"], source=raw["source"], source_job_id=raw["source_job_id"],
            content_hash=raw["content_hash"], why=raw["why"],
            must_haves=_alternatives(raw["must_haves"]),
            archetype=tuple(raw["archetype"]), work_mode=raw["work_mode"],
            years_required=tuple(raw["years_required"]),
            nice_to_haves=_alternatives(raw.get("nice_to_haves", [])),
            one_entry=tuple(_alternatives(group) for group in raw.get("one_entry", [])),
            not_must_haves=tuple(raw.get("not_must_haves", [])),
        ))
    return cases


def normalize(text: str) -> str:
    """Lowercase, punctuation to spaces (keeping + and #), single spaces: "CI/CD" -> "ci cd"."""
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", text.lower()).split())


def _names(item: dict[str, Any]) -> set[str]:
    """Every name an entry goes by, split the way fit scoring splits them, so "Data modeling or
    data integration" and "Electronic Health Records (EHR)" count under each of their parts."""
    names = (item["skill"], *item["exact_phrases"])
    return {normalize(part) for name in names for part in _split(name)}


def _found(alternatives: tuple[str, ...], items: list[dict[str, Any]]) -> set[int]:
    accepted = {normalize(a) for a in alternatives}
    return {i for i, item in enumerate(items) if _names(item) & accepted}


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
    nice_expected: int = 0
    nice_kept: int = 0  # labeled nice-to-haves listed anywhere in the brief
    nice_lost: tuple[str, ...] = ()
    promoted: tuple[str, ...] = ()  # labeled nice-to-haves listed only as must-haves
    groups_total: int = 0
    groups_kept: int = 0  # either/or groups not split across several must-haves
    functions_listed: tuple[str, ...] = ()  # job functions wrongly listed as skills
    error: str | None = None


def score_case(case: GoldenCase, brief: dict[str, Any]) -> CaseScore:
    must, nice = brief["must_haves"], brief["nice_to_haves"]
    hits, matched, missed, misplaced = 0, set(), [], []
    for alternatives in case.must_haves:
        found = _found(alternatives, must)
        if found:
            hits += 1
            matched |= found
        else:
            missed.append(alternatives[0])
            if _found(alternatives, nice):
                misplaced.append(alternatives[0])
    nice_kept, nice_lost, promoted = 0, [], []
    for alternatives in case.nice_to_haves:
        in_nice, in_must = _found(alternatives, nice), _found(alternatives, must)
        if in_nice or in_must:
            nice_kept += 1
        else:
            nice_lost.append(alternatives[0])
        if in_must and not in_nice:
            promoted.append(alternatives[0])
    years = brief["years_required"]
    groups_kept = sum(
        len(set().union(*(_found(alternatives, must) for alternatives in group))) <= 1
        for group in case.one_entry
    )
    functions = tuple(f for f in case.not_must_haves if _found((f,), must))
    return CaseScore(
        name=case.name, expected=len(case.must_haves), hits=hits, predicted=len(must),
        matched_predicted=len(matched), missed=tuple(missed), misplaced=tuple(misplaced),
        archetype_ok=None if not case.archetype else brief["archetype"] in case.archetype,
        work_mode_ok=brief["work_mode"] == case.work_mode,
        years_ok=years is None if not case.years_required else years in case.years_required,
        years_got=years, nice_expected=len(case.nice_to_haves), nice_kept=nice_kept,
        nice_lost=tuple(nice_lost), promoted=tuple(promoted),
        groups_total=len(case.one_entry), groups_kept=groups_kept,
        functions_listed=functions,
    )


def failed_case(case: GoldenCase, error: str) -> CaseScore:
    return CaseScore(
        name=case.name, expected=len(case.must_haves), hits=0, predicted=0, matched_predicted=0,
        missed=tuple(m[0] for m in case.must_haves), misplaced=(), archetype_ok=False,
        work_mode_ok=False, years_ok=False, years_got=None,
        nice_expected=len(case.nice_to_haves), nice_lost=tuple(n[0] for n in case.nice_to_haves),
        error=error,
    )


@dataclass
class Totals:
    hits: int = 0
    expected: int = 0
    matched_predicted: int = 0
    predicted: int = 0
    nice_kept: int = 0
    nice_expected: int = 0
    promoted: int = 0
    groups_kept: int = 0
    groups_total: int = 0
    functions_listed: int = 0
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
            t.nice_kept += s.nice_kept
            t.nice_expected += s.nice_expected
            t.promoted += len(s.promoted)
            t.groups_kept += s.groups_kept
            t.groups_total += s.groups_total
            t.functions_listed += len(s.functions_listed)
            if s.archetype_ok is not None:
                t.archetype_scored += 1
                t.archetype_ok += s.archetype_ok
            t.work_mode_ok += s.work_mode_ok
            t.years_ok += s.years_ok
        return t


def compare(current: Totals, proposed: Totals) -> list[str]:
    """Why the proposal is worse than the current prompt; [] means it may be adopted."""
    problems = []
    if proposed.hits < current.hits - TOLERANCE:
        problems.append(f"must-haves found {proposed.hits} < {current.hits} (tolerance 1)")
    if proposed.nice_kept < current.nice_kept - TOLERANCE:
        problems.append(
            f"nice-to-haves kept {proposed.nice_kept} < {current.nice_kept} (tolerance 1)"
        )
    if proposed.promoted > current.promoted + TOLERANCE:
        problems.append(
            f"nice-to-haves promoted to must {proposed.promoted} > {current.promoted} "
            "(tolerance 1)"
        )
    if proposed.groups_kept < current.groups_kept:
        problems.append(f"either/or groups kept {proposed.groups_kept} < {current.groups_kept}")
    if proposed.functions_listed > current.functions_listed:
        problems.append(
            f"job functions listed {proposed.functions_listed} > {current.functions_listed}"
        )
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
    briefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    candidates: dict[str, Candidate] = field(default_factory=dict)
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
        result.candidates[case.name] = candidate
        request = build_request(skill, BRIEF_SCHEMA, candidate.data(), settings)
        try:
            answer = ask(conn, client, request)
        except LlmError as exc:
            result.scores.append(failed_case(case, str(exc)))
            continue
        if not answer.cached:
            result.cost_usd += answer.cost_usd or 0.0
        result.briefs[case.name] = answer.output
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
        if s.nice_lost:
            flags.append("nice-to-have lost: " + ", ".join(s.nice_lost))
        if s.promoted:
            flags.append("promoted to must: " + ", ".join(s.promoted))
        if s.groups_kept < s.groups_total:
            flags.append(f"split either/or groups: {s.groups_total - s.groups_kept}")
        if s.functions_listed:
            flags.append("job function as skill: " + ", ".join(s.functions_listed))
        lines.append(
            f"- {s.name}: must-haves {s.hits}/{s.expected}, nice kept "
            f"{s.nice_kept}/{s.nice_expected}, listed {s.predicted}"
            + (f" · {'; '.join(flags)}" if flags else " · all right")
        )
    lines += [
        "",
        f"must-haves found: {_pct(t.hits, t.expected)}",
        f"nice-to-haves kept: {_pct(t.nice_kept, t.nice_expected)}",
        f"nice-to-haves promoted to must: {t.promoted}",
        f"either/or groups kept in one entry: {_pct(t.groups_kept, t.groups_total)}",
        f"job functions listed as skills: {t.functions_listed}",
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


# ---------------------------------------------------------------- review page

_ZH = {
    "analytics_engineer": "分析工程师", "pipeline_de": "数据管道 DE", "infra_de": "偏软件/基础设施",
    "remote": "远程", "hybrid": "混合", "onsite": "坐班", "unclear": "没写清",
}
_STYLE = """
:root { --bg:#fbfaf7; --fg:#222; --muted:#666; --card:#fff; --line:#e4e1da; --ok:#1d7a3a;
        --miss:#b3261e; --mark:#fff1a8; --mark2:#d9ecff; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#1b1b1d; --fg:#e8e6e1; --muted:#a3a09a; --card:#242427; --line:#3a3a3e;
          --ok:#6fcf8b; --miss:#ff8a80; --mark:#6b5d12; --mark2:#1f4566; } }
body { background:var(--bg); color:var(--fg); margin:0; padding:16px;
       font:15px/1.6 system-ui, "Microsoft YaHei", sans-serif; }
main { max-width:1300px; margin:0 auto; } h1 { font-size:22px; }
h2 { font-size:18px; margin:0 0 4px; } h4 { margin:12px 0 6px; }
section { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:16px; margin:16px 0; }
.why { color:var(--muted); margin:0 0 8px; }
.cols { display:grid; grid-template-columns:1fr 1.4fr; gap:20px; }
@media (max-width:800px) { .cols { grid-template-columns:1fr; } }
.body { max-height:560px; overflow:auto; border:1px solid var(--line); border-radius:8px;
        padding:10px; font-size:14px; }
ul { padding-left:18px; margin:4px 0; } li.ok { color:var(--ok); } li.miss { color:var(--miss); }
mark { background:var(--mark); color:inherit; padding:0 2px; border-radius:3px; }
mark.nice { background:var(--mark2); }
a { color:inherit; }
"""


def _highlight(text: str, must: list[str], nice: list[str]) -> str:
    out = html.escape(text)
    tagged = [(p, "") for p in must] + [(p, "nice") for p in nice]
    seen: set[str] = set()
    for phrase, css in sorted(tagged, key=lambda pc: len(pc[0]), reverse=True):
        key = phrase.lower()
        if len(phrase) < 2 or key in seen:
            continue
        seen.add(key)
        pattern = r"(?<![A-Za-z0-9>])(" + re.escape(html.escape(phrase)) + r")(?![A-Za-z0-9<])"
        cls = f' class="{css}"' if css else ""
        out = re.sub(pattern, rf"<mark{cls}>\1</mark>", out, flags=re.IGNORECASE)
    return out.replace("\n", "<br>")


def _label_list(entries: tuple[tuple[str, ...], ...], bad: tuple[str, ...], empty: str) -> str:
    items = [
        f"<li class='{'miss' if alts[0] in bad else 'ok'}'>{'✗' if alts[0] in bad else '✓'} "
        + html.escape(" 或 ".join(alts)) + "</li>"
        for alts in entries
    ]
    return f"<ul>{''.join(items) or f'<li>{empty}</li>'}</ul>"


def review_page(cases: list[GoldenCase], ev: Evaluation) -> str:
    """Each posting's cleaned text beside its labels and the brief from `ev`."""
    scores = {s.name: s for s in ev.scores}
    sections = []
    for case in cases:
        candidate, brief, score = (
            ev.candidates.get(case.name), ev.briefs.get(case.name), scores.get(case.name)
        )
        if candidate is None:
            continue
        missed = score.missed if score else ()
        lost = (score.nice_lost + score.promoted) if score else ()
        ai = "<p>（没有回答）</p>"
        if brief:
            def skills(items: list[dict[str, Any]]) -> str:
                return ", ".join(html.escape(i["skill"]) for i in items) or "（无）"
            ai = (
                f"<p><b>必备：</b>{skills(brief['must_haves'])}</p>"
                f"<p><b>加分：</b>{skills(brief['nice_to_haves'])}</p>"
                f"<p><b>岗位类型：</b>{_ZH.get(brief['archetype'], brief['archetype'])} · "
                f"<b>工作方式：</b>{_ZH.get(brief['work_mode'], brief['work_mode'])} · "
                f"<b>年限：</b>{brief['years_required']}</p>"
            )
        must_phrases = [a for alts in case.must_haves for a in alts]
        nice_phrases = [a for alts in case.nice_to_haves for a in alts]
        if brief:
            must_phrases += [p for m in brief["must_haves"] for p in m["exact_phrases"]]
            nice_phrases += [p for m in brief["nice_to_haves"] for p in m["exact_phrases"]]
        years = "、".join(str(y) for y in case.years_required) or "不写（空）"
        archetype = "、".join(_ZH.get(a, a) for a in case.archetype) or "不打分"
        sections.append(f"""
<section>
  <h2>{html.escape(case.name)}</h2>
  <p class="why">{html.escape(case.why)} ·
     <a href="{html.escape(candidate.url)}" target="_blank" rel="noopener">打开原始招聘页</a></p>
  <div class="cols">
    <div>
      <h4>标准答案</h4>
      <p><b>必备技能</b>（✓ AI 找到了，✗ AI 漏了）</p>
      {_label_list(case.must_haves, missed, "（无：不应该编出任何技能）")}
      <p><b>加分技能</b>（✓ AI 保留了，✗ AI 漏了或错放进了必备）</p>
      {_label_list(case.nice_to_haves, lost, "（没有单独标）")}
      <p><b>岗位类型：</b>{archetype} · <b>工作方式：</b>
         {_ZH.get(case.work_mode, case.work_mode)} · <b>年限：</b>{years}</p>
      <h4>AI 的回答（{html.escape(ev.label)}）</h4>
      {ai}
    </div>
    <div>
      <h4>职位原文（黄色 = 必备，蓝色 = 加分）</h4>
      <div class="body">{_highlight(candidate.cleaned_text, must_phrases, nice_phrases)}</div>
    </div>
  </div>
</section>""")
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>标准答案核对</title>
<style>{_STYLE}</style></head><body><main>
<h1>标准答案核对（{len(sections)} 个职位）</h1>
<p>左边是标准答案和 AI 的回答，右边是职位原文。只要看原文"要求"部分：必须的那一段对应必备，
Preferred / a plus / 只在职责里出现的具体技术对应加分。
这个文件只在本机（output 文件夹，不会上传）。</p>
{''.join(sections)}
</main></body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.evaluate_prompt")
    parser.add_argument("proposal", nargs="?", help="a proposed jd-analysis SKILL.md")
    parser.add_argument("--effort", choices=LLM_EFFORTS, help="effort for the proposal")
    parser.add_argument("--review", action="store_true", help=f"write {REVIEW_PAGE.name}")
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
        shown, problems = base, []
        if args.proposal:
            path = Path(args.proposal)
            proposed = parse_skill(path.read_text(encoding="utf-8"), str(path))
            if proposed.name != current.name or proposed.version < current.version:
                print(f"FAIL {path} should be {current.name} at version >= {current.version}")
                return 1
            proposed_settings = replace(settings, effort=args.effort or settings.effort)
            shown = evaluate(conn, client, proposed_settings, proposed, cases)
            print()
            print(format_evaluation(shown))
            problems = compare(base.totals, shown.totals)
            print()
            print("VERDICT: " + ("FAIL\n  - " + "\n  - ".join(problems) if problems else "PASS"))
        if args.review:
            REVIEW_PAGE.parent.mkdir(exist_ok=True)
            REVIEW_PAGE.write_text(review_page(cases, shown), encoding="utf-8")
            print(f"review page: {REVIEW_PAGE}")
        return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
