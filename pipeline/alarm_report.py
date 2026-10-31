"""Show how the current gate version sorted postings, with the reasons a person needs to check.

    uv run python -m pipeline.alarm_report                 # counts + every review/block posting
    uv run python -m pipeline.alarm_report --show benign   # spot-check what was let through
    uv run python -m pipeline.alarm_report --show all --limit 20

This is step 2 of the rules loop (decision #22): what a person reads before labeling.
"""

import argparse
import sys

import psycopg

from pipeline.db import connect
from pipeline.safety_gate import GATE_VERSION

TIERS = ("clean", "benign", "review", "block")


def tier_counts(conn: psycopg.Connection, gate_version: str = GATE_VERSION) -> dict[str, int]:
    rows = conn.execute(
        "select triage, count(*) from gate.results where gate_version = %s group by triage",
        (gate_version,),
    ).fetchall()
    counts = dict.fromkeys(TIERS, 0)
    counts.update({tier: n for tier, n in rows})
    return counts


def flagged_postings(
    conn: psycopg.Connection, tiers: list[str], limit: int, gate_version: str = GATE_VERSION
) -> list[tuple]:
    return conn.execute(
        "select r.triage, p.source, p.company, p.source_job_id,"
        "  coalesce(p.payload->>'title', p.payload->>'text'),"
        "  coalesce(p.payload->>'absolute_url', p.payload->>'hostedUrl'),"
        "  r.triage_reasons, r.findings"
        " from gate.results r join raw.job_postings p using (posting_version_id)"
        " where r.gate_version = %s and r.triage = any(%s)"
        " order by array_position(%s, r.triage), p.company, p.posting_version_id"
        " limit %s",
        (gate_version, tiers, ["block", "review", "benign", "clean"], limit),
    ).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate triage report.")
    parser.add_argument(
        "--show",
        choices=["flagged", "benign", "all"],
        default="flagged",
        help="flagged = review + block (default); all = review + block + benign",
    )
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)
    tiers = {
        "flagged": ["block", "review"],
        "benign": ["benign"],
        "all": ["block", "review", "benign"],
    }

    with connect() as conn:
        counts = tier_counts(conn)
        rows = flagged_postings(conn, tiers[args.show], args.limit)

    print(f"gate version {GATE_VERSION}: " + ", ".join(f"{t} {counts[t]}" for t in TIERS))
    if not rows:
        print(f"\nnothing to show for --show {args.show}")
    for n, (tier, source, company, job_id, title, url, reasons, findings) in enumerate(rows, 1):
        print(f"\n#{n} [{tier.upper()}] {source}/{company} {job_id} | {title}")
        if url:
            print(f"   {url}")
        for reason in reasons:
            print(f"   - {reason}")
        for line in findings.get("instruction_like") or []:
            print(f"   flagged line: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
