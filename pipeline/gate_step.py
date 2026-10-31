"""Run the safety gate over every posting version that hasn't been checked by the current
GATE_VERSION, and store the results (including the triage tier) in gate.results.

Safe to re-run: postings already checked by this version are skipped. After a rule change
(a new GATE_VERSION), every posting is checked again from raw; old results stay as history.
"""

from collections import Counter
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

from ingestion.sources import get_source
from pipeline.safety_gate import GATE_VERSION, run_gate


@dataclass(frozen=True)
class GateCounts:
    checked: int
    alarmed: int
    tiers: dict[str, int] = field(default_factory=dict)  # e.g. {"clean": 2286, "benign": 14}


def gate_pending(conn: psycopg.Connection) -> GateCounts:
    rows = conn.execute(
        "select p.posting_version_id, p.source, p.payload"
        " from raw.job_postings p"
        " where not exists ("
        "   select 1 from gate.results r"
        "   where r.posting_version_id = p.posting_version_id and r.gate_version = %s)"
        " order by p.posting_version_id",
        (GATE_VERSION,),
    ).fetchall()

    alarmed = 0
    tiers: Counter[str] = Counter()
    with conn.transaction():
        for posting_version_id, source, payload in rows:
            result = run_gate(get_source(source).posting_html(payload), "html")
            conn.execute(
                "insert into gate.results"
                " (posting_version_id, gate_version, cleaned_text, findings, verdict, alarmed,"
                "  triage, triage_reasons)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s)"
                " on conflict do nothing",
                (
                    posting_version_id,
                    result.gate_version,
                    result.cleaned_text,
                    Jsonb(result.findings),
                    result.verdict,
                    result.alarmed,
                    result.triage,
                    Jsonb(list(result.triage_reasons)),
                ),
            )
            alarmed += result.alarmed
            tiers[result.triage] += 1
    return GateCounts(checked=len(rows), alarmed=alarmed, tiers=dict(tiers))
