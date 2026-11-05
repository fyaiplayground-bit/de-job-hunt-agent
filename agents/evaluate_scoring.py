"""What would a proposed jd-analysis prompt and skill vocabulary do to real jobs' scores?

    uv run python -m agents.evaluate_scoring --jd-proposal config/proposals/jd-analysis.v4.md \
        --vocabulary config/proposals/skill_vocabulary.v2.toml --jobs 60127 59989 --review

Reports two things:

  vocabulary  every current brief scored under the current and the proposed vocabulary (free)
  jobs        the given jobs briefed again under the proposed prompt (paid, cached), then scored
              under the proposed vocabulary: score, decision and must-haves, before and after

Nothing is stored as a brief or a score, and no real config changes. --review writes
output/scoring_review.html (local, not committed): each job's posting beside what changed, so a
person can check the new reading against the source. The golden set is checked separately, by
agents.evaluate_prompt.
"""

import argparse
import html
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from agents.evaluate_prompt import _highlight
from agents.fit_scoring import (
    FitResult,
    Rules,
    Vocabulary,
    load_briefs,
    load_rules,
    load_vocabulary,
    score_brief,
)
from agents.jd_analysis import brief_postings
from agents.llm import AnthropicClient
from agents.profile import Profile, load_profile
from agents.skills import load_skill, parse_skill
from pipeline.config import REPO_ROOT, llm_settings, profile_dir
from pipeline.db import connect

REVIEW_PAGE = REPO_ROOT / "output" / "scoring_review.html"
DECISION_LABEL = {"apply_referral": "投 + 找内推", "apply": "投", "skip": "跳过"}


@dataclass(frozen=True)
class JobChange:
    posting_version_id: int
    old_brief: dict[str, Any]
    new_brief: dict[str, Any]
    text: str
    before: FitResult
    after: FitResult

    @property
    def decision_changed(self) -> bool:
        return self.before.decision != self.after.decision


def compare_vocabularies(
    briefs: list[tuple[int, dict[str, Any], str]],
    profile: Profile,
    rules: Rules,
    current: Vocabulary,
    proposed: Vocabulary,
    today: date,
) -> tuple[Counter, Counter, list[tuple[int, dict[str, Any], FitResult, FitResult]]]:
    """Decision counts under each vocabulary, and every job whose score moves."""
    before: Counter = Counter()
    after: Counter = Counter()
    moved = []
    for posting_version_id, brief, text in briefs:
        old = score_brief(brief, profile, rules, current, today, text)
        new = score_brief(brief, profile, rules, proposed, today, text)
        before[old.decision] += 1
        after[new.decision] += 1
        if (old.score, old.decision) != (new.score, new.decision):
            moved.append((posting_version_id, brief, old, new))
    return before, after, moved


def _label(result: FitResult) -> str:
    return f"{DECISION_LABEL[result.decision]} · {result.score} 分"


def _skills(result: FitResult, brief: dict[str, Any]) -> str:
    covered = {match.asked for match in result.covered}
    return "".join(
        f'<li class="{"ok" if item["skill"] in covered else "gap"}">'
        f"{'✓' if item['skill'] in covered else '✗'} {html.escape(item['skill'])}</li>"
        for item in brief["must_haves"]
    )


def _job_html(change: JobChange) -> str:
    brief = change.new_brief
    url = brief.get("url", "")
    link = f' · <a href="{html.escape(url)}">原帖</a>' if url.startswith("http") else ""
    must = [
        phrase
        for item in (*change.old_brief["must_haves"], *brief["must_haves"])
        for phrase in item["exact_phrases"]
    ]
    return f"""<article>
<h3>#{change.posting_version_id} {html.escape(brief["company"])} —
{html.escape(brief["title"])}{link}</h3>
<p>{_label(change.before)} → <b>{_label(change.after)}</b> · 必备覆盖
{(change.before.must_have_coverage or 0):.0%} → {(change.after.must_have_coverage or 0):.0%}</p>
<div class="cols">
<div><h4>现在的必备技能（{len(change.old_brief["must_haves"])} 条）</h4>
<ul>{_skills(change.before, change.old_brief)}</ul></div>
<div><h4>新提示词的必备技能（{len(brief["must_haves"])} 条）</h4>
<ul>{_skills(change.after, brief)}</ul></div>
<div class="wide"><h4>职位原文（黄色是提到的技能）</h4>
<div class="body">{_highlight(change.text, must, [])}</div></div>
</div></article>"""


def review_page(
    changes: list[JobChange],
    before: Counter,
    after: Counter,
    moved: list[tuple[int, dict[str, Any], FitResult, FitResult]],
) -> str:
    rows = "".join(
        f"<tr><td>#{posting_version_id}</td><td>{html.escape(brief['company'])} — "
        f"{html.escape(brief['title'])}</td><td>{_label(old)} → {_label(new)}</td></tr>"
        for posting_version_id, brief, old, new in moved
    )
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>打分改动检查</title>
<style>
  body {{ margin: 0 auto; max-width: 1200px; padding: 16px; color: #222; background: #fff;
         font: 14px/1.55 system-ui, sans-serif; }}
  h1 {{ font-size: 20px; }} h2 {{ font-size: 16px; margin-top: 28px; }}
  h3, h4 {{ font-size: 14px; margin: 8px 0 4px; }}
  article {{ border: 1px solid #ccc; padding: 8px 12px; margin-bottom: 16px; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; }}
  .wide {{ grid-column: 1 / -1; }}
  .body {{ max-height: 320px; overflow: auto; background: #f6f6f6; padding: 8px; font-size: 13px; }}
  ul {{ margin: 0; padding-left: 18px; }} .ok {{ color: #1d7a3a; }} .gap {{ color: #a30000; }}
  mark {{ background: #ffe08a; color: #000; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; }}
</style></head><body>
<h1>打分改动：会改变什么</h1>
<p>这只是预览，还没有改动任何东西。✓ 是档案覆盖到的，✗ 是缺口。</p>
<h2>用新提示词重新拆解的职位（{len(changes)} 个）</h2>
{"".join(_job_html(change) for change in changes)}
<h2>只加词表、不重新拆解：全部 {sum(before.values())} 个现有职位</h2>
<p>决定的数量：{dict(before)} → {dict(after)}。分数变了的有 {len(moved)} 个：</p>
<table><tr><th>编号</th><th>职位</th><th>变化</th></tr>{rows}</table>
</body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.evaluate_scoring")
    parser.add_argument("--jd-proposal", type=Path, required=True)
    parser.add_argument("--vocabulary", type=Path, required=True)
    parser.add_argument("--jobs", type=int, nargs="+", required=True)
    parser.add_argument("--review", action="store_true", help=f"also write {REVIEW_PAGE.name}")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    settings = llm_settings()
    profile, rules, today = load_profile(profile_dir()), load_rules(), date.today()
    current_vocab, proposed_vocab = load_vocabulary(), load_vocabulary(args.vocabulary)
    proposal = parse_skill(args.jd_proposal.read_text(encoding="utf-8"), str(args.jd_proposal))
    prompt_version = load_skill("jd-analysis").prompt_version
    with connect() as conn:
        rows = load_briefs(conn, prompt_version, settings.model)
        rebriefed, paid = brief_postings(conn, AnthropicClient(), settings, proposal, args.jobs)

    before, after, moved = compare_vocabularies(
        rows, profile, rules, current_vocab, proposed_vocab, today
    )
    print(f"vocabulary only, {len(rows)} briefs: {dict(before)} -> {dict(after)}")
    for posting_version_id, brief, old, new in moved:
        print(
            f"  #{posting_version_id} {brief['company']} | {brief['title']}: "
            f"{old.decision} {old.score} -> {new.decision} {new.score}"
        )

    old_briefs = {posting_version_id: brief for posting_version_id, brief, _ in rows}
    changes = []
    for posting_version_id, (brief, text) in rebriefed.items():
        old_brief = old_briefs.get(posting_version_id)
        if old_brief is None:
            print(f"  #{posting_version_id}: no current brief to compare with")
            continue
        changes.append(
            JobChange(
                posting_version_id,
                old_brief,
                brief,
                text,
                score_brief(old_brief, profile, rules, current_vocab, today, text),
                score_brief(brief, profile, rules, proposed_vocab, today, text),
            )
        )
    print(f"{proposal.prompt_version} on {len(changes)} jobs (paid ${paid:.2f}):")
    for change in changes:
        print(
            f"  #{change.posting_version_id} {change.new_brief['company']} | "
            f"{change.new_brief['title']}: {change.before.decision} {change.before.score} "
            f"-> {change.after.decision} {change.after.score}, must-haves "
            f"{len(change.old_brief['must_haves'])} -> {len(change.new_brief['must_haves'])}; "
            f"gaps now: {', '.join(change.after.not_covered)}"
        )
    if args.review:
        REVIEW_PAGE.parent.mkdir(exist_ok=True)
        REVIEW_PAGE.write_text(review_page(changes, before, after, moved), encoding="utf-8")
        print(f"review page: {REVIEW_PAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
