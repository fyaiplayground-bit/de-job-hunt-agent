"""Rules loop step B (decision #23): record a person's judgment of an alarmed posting, and turn
the labels into golden cases that every future rules change must respect.

    uv run python -m pipeline.labels add 1234 false_positive --note "describes team culture"
    uv run python -m pipeline.labels list
    uv run python -m pipeline.labels export     # -> tests/fixtures/gate_cases_labeled.jsonl

Only the flagged line goes into the golden set, never the whole posting: postings are other
companies' text, and the repo is public.
"""

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from pipeline.alarm_triage import visible_line
from pipeline.db import connect, migrate
from pipeline.safety_gate import GATE_VERSION

LABELS = ("false_positive", "attack", "unsure")
LABELED_CASES_FILE = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "gate_cases_labeled.jsonl"
)


class LabelError(ValueError):
    """A label that can't be recorded (unknown label, or no gate result to label)."""


def flagged_lines(findings: dict[str, Any], cleaned_text: str) -> list[str]:
    """The lines a person reads to judge a posting: each flagged line in full when it's visible,
    the excerpt when it came from hidden content, plus decoded invisible text and look-alikes."""
    lines = [visible_line(e, cleaned_text) or e for e in findings.get("instruction_like") or []]
    lines += [f"[invisible text] {t}" for t in findings.get("invisible_text") or []]
    if findings.get("homoglyph_runs"):
        lines.append("[look-alike letters] " + " ".join(findings["homoglyph_runs"]))
    return lines


def add_label(
    conn: psycopg.Connection,
    posting_version_id: int,
    label: str,
    note: str | None = None,
    labeled_by: str = "FL",
    gate_version: str = GATE_VERSION,
) -> int:
    """Record one label for one posting version, judged under `gate_version`. Returns its id."""
    if label not in LABELS:
        raise LabelError(f"label must be one of {LABELS}, got {label!r}")
    row = conn.execute(
        "select triage, findings, cleaned_text from gate.results"
        " where posting_version_id = %s and gate_version = %s",
        (posting_version_id, gate_version),
    ).fetchone()
    if row is None:
        raise LabelError(
            f"posting {posting_version_id} has no gate result for version {gate_version}"
        )
    tier, findings, cleaned_text = row
    return conn.execute(
        "insert into gate.labels (posting_version_id, label, note, labeled_by, gate_version,"
        "  tier_at_label, flagged_lines)"
        " values (%s, %s, %s, %s, %s, %s, %s) returning label_id",
        (
            posting_version_id,
            label,
            note,
            labeled_by,
            gate_version,
            tier,
            Jsonb(flagged_lines(findings, cleaned_text)),
        ),
    ).fetchone()[0]


def latest_labels(conn: psycopg.Connection) -> list[tuple]:
    """The current label of every labeled posting (newer labels supersede older ones)."""
    return conn.execute(
        "select distinct on (l.posting_version_id)"
        "  l.posting_version_id, l.label, l.note, l.labeled_by, l.labeled_at, l.gate_version,"
        "  l.tier_at_label, p.company, coalesce(p.payload->>'title', p.payload->>'text')"
        " from gate.labels l join raw.job_postings p using (posting_version_id)"
        " order by l.posting_version_id, l.labeled_at desc, l.label_id desc"
    ).fetchall()


def _tag_spelled(text: str) -> str:
    return "".join(chr(0xE0000 + ord(c)) for c in text)


def case_inputs(findings: dict[str, Any], cleaned_text: str) -> list[tuple[str, str]]:
    """Minimal (mode, text) inputs that reproduce what the gate flagged, without the posting.

    A visible line stays a visible line; a line from hidden content is re-hidden; invisible
    text is re-spelled in tag characters; look-alike words are kept as they were.
    """
    inputs = []
    for excerpt in findings.get("instruction_like") or []:
        line = visible_line(excerpt, cleaned_text)
        if line is not None:
            inputs.append(("text", f"Job.\n{line}\n"))
        else:
            hidden = html.escape(excerpt.strip("…"))
            inputs.append(("html", f'<p>Job.</p><div style="display:none">{hidden}</div>'))
    for decoded in findings.get("invisible_text") or []:
        inputs.append(("text", f"Job.\n{_tag_spelled(decoded)}\n"))
    if findings.get("homoglyph_runs") and not inputs:
        inputs.append(("text", "Job.\n" + " ".join(findings["homoglyph_runs"]) + "\n"))
    return inputs


def export_cases(conn: psycopg.Connection, path: Path = LABELED_CASES_FILE) -> int:
    """Write every labeled false positive and attack as golden cases. Unsure labels are left out.

    Identical inputs from several postings (one template on ten job pages) become one case that
    lists all of them. Output order is fixed, so re-exporting the same labels changes nothing.
    """
    cases: dict[tuple[str, str], dict[str, Any]] = {}
    for posting_id, label, note, by, at, gate_version, _tier, company, title in latest_labels(conn):
        if label == "unsure":
            continue
        findings, cleaned_text = conn.execute(
            "select findings, cleaned_text from gate.results"
            " where posting_version_id = %s and gate_version = %s",
            (posting_id, gate_version),
        ).fetchone()
        for mode, text in case_inputs(findings, cleaned_text):
            case = cases.setdefault(
                (mode, text),
                {
                    "kind": label,
                    "mode": mode,
                    "text": text,
                    "origin": f"label by {by} {at:%Y-%m-%d}: {company} | {title}",
                    "why": note or "",
                    "postings": [],
                },
            )
            if case["kind"] != label:  # same line labeled both ways: the safer label wins
                case["kind"] = "attack"
            case["postings"].append(posting_id)

    ordered = sorted(cases.values(), key=lambda c: (c["kind"], min(c["postings"]), c["text"]))
    lines = []
    for n, case in enumerate(ordered, 1):
        case["postings"] = sorted(case["postings"])
        lines.append(json.dumps({"id": f"label-{n:03d}", **case}, ensure_ascii=True))
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    return len(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Label alarmed postings (rules loop step B).")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="record a label")
    add.add_argument("posting_version_id", type=int, nargs="+")
    add.add_argument("label", choices=LABELS)
    add.add_argument("--note")
    add.add_argument("--by", default="FL")
    sub.add_parser("list", help="show the current label of every labeled posting")
    sub.add_parser("export", help=f"write golden cases to {LABELED_CASES_FILE.name}")
    args = parser.parse_args(argv)

    with connect() as conn:
        migrate(conn)
        if args.command == "add":
            for posting_id in args.posting_version_id:
                label_id = add_label(conn, posting_id, args.label, args.note, args.by)
                print(f"label {label_id}: posting {posting_id} -> {args.label}")
        elif args.command == "list":
            for posting_id, label, note, by, at, _v, tier, company, title in latest_labels(conn):
                print(f"{posting_id:>7}  {label:14} (was {tier:6}) {company:12} {title[:50]}")
                if note:
                    print(f"         note: {note}  [{by}, {at:%Y-%m-%d}]")
        else:
            n = export_cases(conn)
            print(f"{n} golden cases -> {LABELED_CASES_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
