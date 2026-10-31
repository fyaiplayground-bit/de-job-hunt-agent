"""Rules loop step 5 (decision #23): what would a proposed triage rules file change?

    uv run python -m pipeline.evaluate_rules config/proposals/triage_rules.v2.toml

Judges every golden case and every stored posting under the current rules and the proposed
ones, then reports:

  hard checks  must all pass, or the proposal is rejected (exit code 1):
               - every hand-written golden case lands in its expected tier
               - no attack (hand-written or labeled) comes out benign or clean
               - no labeled false positive comes out block
  soft         labeled false positives that are benign (noise a person no longer has to read)
  postings     tier counts before/after, and every posting whose tier would change

Nothing is written anywhere: the database and the real rules file are only read.
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from ingestion.sources import get_source
from pipeline import posting_guard
from pipeline.alarm_triage import RULES_FILE, TriageRules, load_rules, triage
from pipeline.db import connect
from pipeline.labels import LABELED_CASES_FILE
from pipeline.safety_gate import is_alarmed, run_gate

HAND_CASES_FILE = LABELED_CASES_FILE.with_name("gate_cases.jsonl")
TIERS = ("clean", "benign", "review", "block")


def load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@dataclass
class Evaluation:
    current_version: int
    proposed_version: int
    hard_failures: list[str] = field(default_factory=list)
    fp_benign: tuple[int, int] = (0, 0)  # labeled false positives that are benign: now, proposed
    fp_total: int = 0
    tier_counts: dict[str, Counter] = field(default_factory=dict)  # "current"/"proposed" -> counts
    changed: list[tuple] = field(default_factory=list)  # (posting id, company, title, from, to)

    @property
    def passed(self) -> bool:
        return not self.hard_failures


def evaluate_cases(
    hand: list[dict],
    labeled: list[dict],
    current: TriageRules,
    proposed: TriageRules,
    ev: Evaluation,
) -> None:
    for case in hand:
        tier = run_gate(case["text"], case["mode"], proposed).triage
        if tier != case["expect"]:
            ev.hard_failures.append(f"{case['id']}: expected {case['expect']}, got {tier}")
    for case in hand + labeled:
        if case["kind"] == "attack":
            tier = run_gate(case["text"], case["mode"], proposed).triage
            if tier in ("benign", "clean"):
                ev.hard_failures.append(
                    f"{case['id']}: ATTACK would be {tier}: {case['text'][:80]!r}"
                )
    fps = [c for c in labeled if c["kind"] == "false_positive"]
    now = sum(run_gate(c["text"], c["mode"], current).triage == "benign" for c in fps)
    then = 0
    for case in fps:
        tier = run_gate(case["text"], case["mode"], proposed).triage
        then += tier == "benign"
        if tier == "block":
            ev.hard_failures.append(f"{case['id']}: false positive would be blocked")
    ev.fp_benign, ev.fp_total = (now, then), len(fps)


def evaluate_postings(
    conn: psycopg.Connection, current: TriageRules, proposed: TriageRules, ev: Evaluation
) -> None:
    """Re-judge every stored posting from raw under both rule sets (detection runs once)."""
    rows = conn.execute(
        "select posting_version_id, source, company, payload,"
        " coalesce(payload->>'title', payload->>'text') from raw.job_postings"
        " order by posting_version_id"
    ).fetchall()
    counts = {"current": Counter(), "proposed": Counter()}
    for posting_id, source, company, payload, title in rows:
        cleaned, findings = posting_guard.guard(get_source(source).posting_html(payload), "html")
        alarmed = is_alarmed(findings)
        before = triage(findings, cleaned, alarmed, current).tier
        after = triage(findings, cleaned, alarmed, proposed).tier
        counts["current"][before] += 1
        counts["proposed"][after] += 1
        if before != after:
            ev.changed.append((posting_id, company, title, before, after))
    ev.tier_counts = counts


def evaluate(
    proposed_path: Path, current_path: Path = RULES_FILE, conn: psycopg.Connection | None = None
) -> Evaluation:
    current, proposed = load_rules(current_path), load_rules(proposed_path)
    ev = Evaluation(current.version, proposed.version)
    evaluate_cases(
        load_cases(HAND_CASES_FILE), load_cases(LABELED_CASES_FILE), current, proposed, ev
    )
    if conn is not None:
        evaluate_postings(conn, current, proposed, ev)
    return ev


def print_report(ev: Evaluation) -> None:
    print(f"rules v{ev.current_version} (current) vs v{ev.proposed_version} (proposed)")
    if ev.proposed_version <= ev.current_version and (
        ev.changed or ev.fp_benign[0] != ev.fp_benign[1]
    ):
        print("WARNING: results change, but the proposed version is not higher than the current")
    print("\nhard checks: " + ("PASS" if ev.passed else f"FAIL ({len(ev.hard_failures)})"))
    for failure in ev.hard_failures:
        print(f"  - {failure}")
    now_benign, proposed_benign = ev.fp_benign
    print(f"\nlabeled false positives benign: {now_benign} -> {proposed_benign} of {ev.fp_total}")
    if ev.tier_counts:
        now, then = ev.tier_counts["current"], ev.tier_counts["proposed"]
        print("\npostings by tier (current -> proposed):")
        for tier in TIERS:
            print(f"  {tier:7} {now[tier]:6} -> {then[tier]:6}")
        print(f"\npostings that would change tier: {len(ev.changed)}")
        for posting_id, company, title, before, after in ev.changed[:50]:
            print(f"  {posting_id:>7} {company:12} {before:>6} -> {after:<6} {title[:50]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a proposed triage rules file.")
    parser.add_argument("proposed", type=Path)
    parser.add_argument("--current", type=Path, default=RULES_FILE)
    parser.add_argument("--no-db", action="store_true", help="golden cases only")
    args = parser.parse_args(argv)

    if args.no_db:
        ev = evaluate(args.proposed, args.current)
    else:
        with connect() as conn:
            ev = evaluate(args.proposed, args.current, conn)
    print_report(ev)
    return 0 if ev.passed else 1


if __name__ == "__main__":
    sys.exit(main())
