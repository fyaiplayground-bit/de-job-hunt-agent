"""Rules loop for fit scoring (decision #35): what would a proposed rules file change?

    uv run python -m agents.evaluate_fit_rules config/proposals/fit_scoring.v2.toml
    uv run python -m agents.evaluate_fit_rules PROPOSAL --review   # + review page

Reports three things:

  golden      every labeled case in tests/fixtures/clearance_cases.toml lands in its tier; any
              miss rejects the proposal (exit code 1)
  moves       every current brief scored under the current rules and the proposal, and each job
              whose decision would change
  all postings  how the clearance rule sorts every DE-titled posting in the database, as a wider
              test than the few jobs briefed so far; with a location check, also where each
              posting's job-board location places it (decision #51)

Nothing is written to the database or the real rules file. --review writes
output/fit_rules_review.html (local, not committed): each moved job's full text with the deciding
words marked (for a location move, its place names side by side with the posting's own words),
and samples from the wider test, so a person can check the rule against the source.
"""

import argparse
import html
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from agents.evaluate_prompt import _highlight
from agents.fit_scoring import (
    ClearanceRules,
    LocationRules,
    Rules,
    Vocabulary,
    find_clearance,
    find_location,
    job_places,
    load_briefs,
    load_rules,
    load_vocabulary,
    match_skill,
    place_verdict,
    score_brief,
)
from agents.jd_analysis import _display_fields, load_scope
from agents.profile import Profile, load_profile
from agents.skills import load_skill
from pipeline.config import REPO_ROOT, profile_dir
from pipeline.db import connect
from pipeline.safety_gate import GATE_VERSION

CASES_FILE = REPO_ROOT / "tests" / "fixtures" / "clearance_cases.toml"
PHRASE_CASES_FILE = REPO_ROOT / "tests" / "fixtures" / "phrase_match_cases.toml"
LOCATION_CASES_FILE = REPO_ROOT / "tests" / "fixtures" / "location_cases.toml"
SAMPLE_PROFILE_DIR = REPO_ROOT / "data" / "sample"
REVIEW_PAGE = REPO_ROOT / "output" / "fit_rules_review.html"
# Any wording about clearance, even wording the rule treats as no requirement.
MENTION = re.compile(r"clearance|TS\s*/\s*SCI|top[- ]secret|polygraph|\bcleared\b", re.IGNORECASE)
SAMPLE_SIZE = {"hold": 25, "obtain": 25, "mention": 40}
PLACE_SAMPLE_SIZE = {"outside_us": 60, "unclear": 40}
WORK_MODE_WORDS = {"remote", "hybrid", "onsite", "on-site"}
PLACE_LABEL = {
    "outside_us": "明确在美国以外（跳过）",
    "unclear": "看不出在哪（保留）",
}
TIER_LABEL = {
    "hold": "必须已经持有（跳过）",
    "obtain": "必须能够取得（跳过，除非档案写明可以取得）",
    "mention": "提到了，但不算要求（保留）",
}


def golden_problems(rules: ClearanceRules, path: Path = CASES_FILE) -> list[str]:
    """Labeled wording that lands in the wrong tier; [] means every case passes."""
    problems = []
    for case in tomllib.loads(path.read_text(encoding="utf-8"))["cases"]:
        hit = find_clearance(case["text"], rules)
        got = hit[0] if hit else "none"
        if got != case["tier"]:
            problems.append(f"want {case['tier']}, got {got}: {case['text']!r}")
    return problems


def location_problems(rules: LocationRules, path: Path = LOCATION_CASES_FILE) -> list[str]:
    """Labeled place lists that land in the wrong place; [] means every case passes."""
    problems = []
    for case in tomllib.loads(path.read_text(encoding="utf-8"))["cases"]:
        got, _ = find_location(case["places"], rules)
        if got != case["where"]:
            problems.append(f"want {case['where']}, got {got}: {case['places']!r}")
    return problems


def phrase_problems(
    rules: Rules, vocab: Vocabulary, profile: Profile, path: Path = PHRASE_CASES_FILE
) -> list[str]:
    """Labeled requirements that match wrongly; [] means every case passes."""
    problems = []
    for case in tomllib.loads(path.read_text(encoding="utf-8"))["cases"]:
        item = {"skill": case["skill"], "exact_phrases": case["phrases"]}
        covered = match_skill(item, profile.bank, vocab, rules.phrase_match).skill is not None
        if covered != case["covered"]:
            problems.append(f"want covered={case['covered']}: {case['skill']} {case['phrases']}")
    return problems


@dataclass(frozen=True)
class Move:
    posting_version_id: int
    brief: dict[str, Any]
    text: str
    before: dict[str, Any]
    after: dict[str, Any]


def compare(
    briefs: list[tuple[int, dict[str, Any], str]],
    profile: Profile,
    current: Rules,
    proposed: Rules,
    vocab: Vocabulary,
    today: date,
    every_score: bool = False,
    proposed_vocab: Vocabulary | None = None,
) -> tuple[Counter, Counter, list[Move]]:
    """Decision counts under each rules file, and the jobs whose decision would change (with
    `every_score`, also those whose score alone would), decisions first."""
    before, after, moves = Counter(), Counter(), []
    for posting_version_id, brief, text in briefs:
        old = score_brief(brief, profile, current, vocab, today, text).as_json()
        new = score_brief(brief, profile, proposed, proposed_vocab or vocab, today, text).as_json()
        before[old["decision"]] += 1
        after[new["decision"]] += 1
        changed = old["decision"] != new["decision"]
        if changed or (every_score and old["score"] != new["score"]):
            moves.append(Move(posting_version_id, brief, text, old, new))
    moves.sort(key=lambda m: (m.before["decision"] == m.after["decision"], -m.before["score"]))
    return before, after, moves


@dataclass(frozen=True)
class Sample:
    posting_version_id: int
    company: str
    title: str
    words: str
    text: str


def sort_postings(
    rows: list[tuple[int, str, str, str]], rules: ClearanceRules
) -> tuple[Counter, dict[str, list[Sample]]]:
    """Each posting's tier under the rule. `mention` = talks about clearance but isn't skipped."""
    counts: Counter = Counter()
    tiers: dict[str, list[Sample]] = {tier: [] for tier in SAMPLE_SIZE}
    for posting_version_id, company, title, text in rows:
        blob = f"{title}\n{text}"
        hit = find_clearance(blob, rules)
        mention = MENTION.search(blob)
        tier = hit[0] if hit else "mention" if mention else "none"
        counts[tier] += 1
        if tier != "none":
            words = hit[1] if hit else mention[0]
            tiers[tier].append(Sample(posting_version_id, company, title, words, blob))
    return counts, tiers


def every_nth(items: list[Sample], size: int) -> list[Sample]:
    """An even spread through the list: the same sample every time."""
    return items if len(items) <= size else items[:: len(items) // size][:size]


def _locate(text: str, words: str) -> re.Match[str] | None:
    # The rule may have dropped a "U.S." between the words, so allow a short gap.
    pattern = r"[\s\S]{0,8}?".join(re.escape(word) for word in words.split())
    return re.search(pattern, text, re.IGNORECASE) if pattern else None


def _marked(text: str, words: str, around: int | None = None) -> str:
    """Escaped text with the words marked; with `around`, only that many characters each side."""
    found = _locate(text, words)
    if not found:
        return html.escape(text if around is None else text[: 2 * (around or 0)])
    start = 0 if around is None else max(0, found.start() - around)
    end = len(text) if around is None else found.end() + around
    return (
        html.escape(text[start : found.start()])
        + "<mark>"
        + html.escape(found[0])
        + "</mark>"
        + html.escape(text[found.end() : end])
    )


def _decision_label(result: dict[str, Any]) -> str:
    return f"{result['decision']} · {result['score']} 分"


def _lost_requirements(move: Move) -> list[str]:
    """Must-haves counted as covered before and not after."""
    still = {match["asked"] for match in move.after["covered"]}
    return [match["asked"] for match in move.before["covered"] if match["asked"] not in still]


def _phrase_move_html(move: Move) -> str:
    """A job moved by how phrases match: what lost credit, in the posting's words."""
    lost = _lost_requirements(move)
    items = {item["skill"]: item for item in move.brief["must_haves"]}
    rows = "".join(
        f"<li><b>{html.escape(name)}</b>: the posting's words were "
        f"{html.escape(' | '.join(items.get(name, {}).get('exact_phrases', [])))}</li>"
        for name in lost
    )
    phrases = [p for name in lost for p in items.get(name, {}).get("exact_phrases", [])]
    url = move.brief.get("url", "")
    link = f' · <a href="{html.escape(url)}">原帖</a>' if url.startswith("http") else ""
    return (
        f"<article><h3>#{move.posting_version_id} {html.escape(move.brief.get('company', ''))} — "
        f"{html.escape(move.brief.get('title', ''))}{link}</h3>"
        f"<p>{_decision_label(move.before)} → <b>{_decision_label(move.after)}</b> · 必备覆盖 "
        f"{(move.before['must_have_coverage'] or 0):.0%} → "
        f"{(move.after['must_have_coverage'] or 0):.0%}</p>"
        f"<p>不再算覆盖的必备技能：</p><ul>{rows}</ul>"
        f"<pre>{_highlight(move.text, phrases, [])}</pre></article>"
    )


def _place_words(place: str) -> list[str]:
    """The parts of a place name worth finding in the posting: "Warsaw, Poland" -> both;
    "Remote - India" -> India (work-mode words say nothing about where)."""
    parts = (w.strip() for w in re.split(r"[^\w\s.'-]+|\s-\s", place))
    return [w for w in parts if len(w) > 2 and w.lower() not in WORK_MODE_WORDS]


def _location_move_html(move: Move) -> str:
    """A job moved by the location check: its place names next to the posting's own words."""
    brief = move.brief
    place = re.search(r"\((['\"])(.*)\1\)$", move.after["dealbreakers"][0])
    decided = place[2] if place else ""
    rows = "".join(
        f"<tr><th>{label}</th><td>{html.escape(value) or '（空）'}</td></tr>"
        for label, value in (
            ("招聘网站写的地点", brief.get("board_location") or ""),
            ("AI 从正文读到的地点", " | ".join(brief.get("locations") or [])),
            ("AI 读到的远程范围", " | ".join(brief.get("remote_regions") or [])),
            ("工作方式", brief.get("work_mode") or ""),
            ("起决定作用的地点", decided),
        )
    )
    found = next((w for w in _place_words(decided) if _locate(move.text, w)), "")
    excerpt = (
        f"<p>正文里提到这个地点的地方：</p><pre>…{_marked(move.text, found, around=300)}…</pre>"
        if found
        else "<p>正文里没有写这个地点（地点只来自招聘网站的字段）。</p>"
    )
    url = brief.get("url", "")
    link = f' · <a href="{html.escape(url)}">原帖</a>' if url.startswith("http") else ""
    return (
        f"<article><h3>#{move.posting_version_id} {html.escape(brief.get('company', ''))} — "
        f"{html.escape(brief.get('title', ''))}{link}</h3>"
        f"<p>{_decision_label(move.before)} → <b>{_decision_label(move.after)}</b></p>"
        f"<table class=places>{rows}</table>{excerpt}</article>"
    )


def _move_html(move: Move) -> str:
    if move.after["dealbreakers"] and move.after["dealbreakers"][0].startswith("location:"):
        return _location_move_html(move)
    if not move.after["dealbreakers"] or _lost_requirements(move):
        return _phrase_move_html(move)
    words = (
        re.search(r"\((['\"])(.*)\1\)$", move.after["dealbreakers"][0])
        if move.after["dealbreakers"]
        else None
    )
    url = move.brief.get("url", "")
    link = f' · <a href="{html.escape(url)}">原帖</a>' if url.startswith("http") else ""
    reason = "；".join(move.after["dealbreakers"]) or "分数变了"
    return (
        f"<article><h3>#{move.posting_version_id} {html.escape(move.brief.get('company', ''))} — "
        f"{html.escape(move.brief.get('title', ''))}{link}</h3>"
        f"<p>{_decision_label(move.before)} → <b>{_decision_label(move.after)}</b><br>"
        f"原因：{html.escape(reason)}</p>"
        f"<pre>{_marked(move.text, words[2] if words else '')}</pre></article>"
    )


def review_page(
    moves: list[Move],
    before: Counter,
    after: Counter,
    counts: Counter,
    tiers: dict[str, list[Sample]],
    current: Rules,
    proposed: Rules,
    places: tuple[Counter, dict[str, list[Sample]]] | None = None,
) -> str:
    moved = "".join(_move_html(move) for move in moves) or "<p>没有职位的决定发生变化。</p>"
    groups = ""
    for tier, label in TIER_LABEL.items():
        chosen = every_nth(tiers[tier], SAMPLE_SIZE[tier])
        rows = "".join(
            f"<tr><td>#{s.posting_version_id}<br>{html.escape(s.company)}</td>"
            f"<td>{html.escape(s.title)}</td><td>…{_marked(s.text, s.words, around=110)}…</td></tr>"
            for s in chosen
        )
        groups += (
            f"<h3>{label}：一共 {counts[tier]} 个，这里抽 {len(chosen)} 个</h3>"
            f"<table><tr><th>职位</th><th>标题</th><th>原文（标出的是起决定作用的词）</th></tr>"
            f"{rows}</table>"
        )
    wider = ""
    if current.clearance != proposed.clearance:
        wider = (
            f"<h2>更大范围的测试：数据库里所有 DE 类职位（一共 {sum(counts.values())} 个）</h2>"
            f"<p>其中 {counts['none']} 个根本没提 clearance，这些不受影响。</p>{groups}"
        )
    if places is not None:
        place_counts, place_tiers = places
        place_groups = ""
        for tier, label in PLACE_LABEL.items():
            chosen = every_nth(place_tiers[tier], PLACE_SAMPLE_SIZE[tier])
            rows = "".join(
                f"<tr><td>#{s.posting_version_id}<br>{html.escape(s.company)}</td>"
                f"<td>{html.escape(s.title)}</td><td>{_marked(s.text, s.words)}</td></tr>"
                for s in chosen
            )
            place_groups += (
                f"<h3>{label}：一共 {place_counts[tier]} 个，这里抽 {len(chosen)} 个</h3>"
                f"<table><tr><th>职位</th><th>标题</th><th>招聘网站写的地点（标出的是起决定作用的词）"
                f"</th></tr>{rows}</table>"
            )
        wider += (
            f"<h2>更大范围的测试：数据库里所有 DE 类职位，按招聘网站写的地点分（一共 "
            f"{sum(place_counts.values())} 个）</h2><p>其中 {place_counts['us']} 个在美国，保留。"
            "这里只看招聘网站的地点字段，不看 AI 从正文读到的地点，"
            "所以“看不出在哪”的会比真实打分时多。</p>"
            + place_groups
        )
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>打分规则检查</title>
<style>
  body {{ margin: 0 auto; max-width: 1000px; padding: 16px; font: 14px/1.55 system-ui, sans-serif;
         color: #222; background: #fff; }}
  h1 {{ font-size: 20px; }} h2 {{ font-size: 16px; margin-top: 28px; }} h3 {{ font-size: 14px; }}
  article {{ border: 1px solid #ccc; padding: 8px 12px; margin-bottom: 12px; }}
  pre {{ white-space: pre-wrap; max-height: 360px; overflow: auto; background: #f6f6f6;
         padding: 8px; font: 13px/1.5 system-ui, sans-serif; }}
  mark {{ background: #ffe08a; color: #000; }}
  table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
  td, th {{ border: 1px solid #ccc; padding: 4px 8px; vertical-align: top; text-align: left;
            overflow-wrap: anywhere; }}
  th:nth-child(1) {{ width: 20%; }} th:nth-child(2) {{ width: 24%; }}
  table.places th {{ width: 22%; background: #f6f6f6; }}
</style></head><body>
<h1>打分规则 v{current.version} → v{proposed.version}：会改变什么</h1>
<p>决定的数量：{dict(before)} → {dict(after)}。这只是预览，还没有改动任何东西。</p>
<h2>会变的职位（{len(moves)} 个，决定变了的排在最前面）</h2>
{moved}
{wider}
</body></html>
"""


def de_postings(conn: psycopg.Connection) -> list[tuple[int, str, str, str]]:
    """Every deduped DE-titled posting, by the title pattern the analysis scope uses."""
    return conn.execute(
        "select p.posting_version_id, p.company, coalesce(p.payload->>'title', p.payload->>'text',"
        " '') as title, g.cleaned_text"
        " from dedupe.jobs j"
        " join raw.job_postings p on p.posting_version_id = j.chosen_posting_version_id"
        " join gate.results g on g.posting_version_id = p.posting_version_id"
        "  and g.gate_version = %s"
        " where coalesce(p.payload->>'title', p.payload->>'text', '') ~* %s"
        " order by p.posting_version_id",
        (GATE_VERSION, load_scope().title_include),
    ).fetchall()


def de_posting_places(conn: psycopg.Connection) -> list[tuple[int, str, str, str]]:
    """Every deduped DE-titled posting with the location its job board gives."""
    rows = conn.execute(
        "select p.posting_version_id, p.source, p.company,"
        " coalesce(p.payload->>'title', p.payload->>'text', '') as title, p.payload"
        " from dedupe.jobs j"
        " join raw.job_postings p on p.posting_version_id = j.chosen_posting_version_id"
        " where coalesce(p.payload->>'title', p.payload->>'text', '') ~* %s"
        " order by p.posting_version_id",
        (load_scope().title_include,),
    ).fetchall()
    out = []
    for posting_version_id, source, company, title, payload in rows:
        name, location, _ = _display_fields(source, company, payload)
        out.append((posting_version_id, name, title, location))
    return out


def sort_places(
    rows: list[tuple[int, str, str, str]], rules: LocationRules
) -> tuple[Counter, dict[str, list[Sample]]]:
    """Where each posting's job-board location places it, with the deciding words."""
    counts: Counter = Counter()
    tiers: dict[str, list[Sample]] = {"us": [], "outside_us": [], "unclear": []}
    for posting_version_id, company, title, location in rows:
        tier, _ = find_location([location] if location.strip() else [], rules)
        words = ""
        if tier != "unclear":
            words = place_verdict(location, rules)[1]
        counts[tier] += 1
        tiers[tier].append(Sample(posting_version_id, company, title, words, location))
    return counts, tiers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.evaluate_fit_rules")
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--review", action="store_true", help=f"also write {REVIEW_PAGE.name}")
    parser.add_argument(
        "--brief-versions",
        nargs="+",
        help="read these jd-analysis versions too, newest brief per job (default: the current one)",
    )
    parser.add_argument("--every-score", action="store_true", help="list score-only moves too")
    parser.add_argument("--vocabulary", type=Path, help="a proposed skill vocabulary")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    current, proposed = load_rules(), load_rules(args.proposal)
    problems = golden_problems(proposed.clearance) if proposed.clearance else []
    vocabulary = load_vocabulary()
    proposed_vocab = load_vocabulary(args.vocabulary) if args.vocabulary else vocabulary
    profile = load_profile(profile_dir())
    # The phrase cases are labeled for the fictional sample, whichever profile is being scored.
    problems += phrase_problems(proposed, proposed_vocab, load_profile(SAMPLE_PROFILE_DIR))
    if proposed.location:
        problems += location_problems(proposed.location)
    print(
        f"rules v{current.version} -> v{proposed.version}, "
        f"vocabulary v{vocabulary.version} -> v{proposed_vocab.version}"
    )
    for problem in problems:
        print(f"  GOLDEN {problem}")
    print(f"golden cases: {'FAIL' if problems else 'PASS'}")

    prompt_version = load_skill("jd-analysis").prompt_version
    with connect() as conn:
        versions = args.brief_versions or [prompt_version]
        newest: dict[int, tuple[int, dict[str, Any], str]] = {}
        for version in versions:  # later versions replace earlier ones
            for row in load_briefs(conn, version):
                newest[row[0]] = row
        briefs = list(newest.values())
        postings = de_postings(conn)
        places = de_posting_places(conn) if proposed.location else []
    before, after, moves = compare(
        briefs,
        profile,
        current,
        proposed,
        vocabulary,
        date.today(),
        args.every_score,
        proposed_vocab,
    )
    print(f"briefs ({', '.join(versions)}): {dict(before)} -> {dict(after)}")
    for move in moves:
        print(
            f"  #{move.posting_version_id} {move.brief.get('company')} | "
            f"{move.brief.get('title')}: {move.before['decision']} {move.before['score']} -> "
            f"{move.after['decision']} {move.after['score']} "
            f"(lost {', '.join(_lost_requirements(move)) or 'nothing'}; "
            f"{'; '.join(move.after['dealbreakers'])})"
        )
    sorted_places = None
    if proposed.location:
        where = Counter(find_location(job_places(b), proposed.location)[0] for _, b, _ in briefs)
        print(f"briefs by place: {dict(where)}")
        sorted_places = sort_places(places, proposed.location)
        print(f"all DE-titled postings by job-board location ({len(places)}): "
              f"{dict(sorted_places[0])}")
    if proposed.clearance:
        counts, tiers = sort_postings(postings, proposed.clearance)
        print(f"all DE-titled postings ({len(postings)}): {dict(counts)}")
        if args.review:
            REVIEW_PAGE.parent.mkdir(exist_ok=True)
            REVIEW_PAGE.write_text(
                review_page(moves, before, after, counts, tiers, current, proposed,
                            sorted_places),
                encoding="utf-8",
            )
            print(f"review page: {REVIEW_PAGE}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
