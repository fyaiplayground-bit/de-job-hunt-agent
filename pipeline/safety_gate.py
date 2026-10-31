"""JD safety gate: every job posting passes through `run_gate()` before any agent reads it.

The detection rules live in `pipeline/posting_guard.py` (copied from ai-job-search); the triage
rules that decide what to do with an alarm live in `pipeline/alarm_triage.py` and
`config/triage_rules.toml`. This module is our interface to both: one function in, one result
object out, plus a version so results can be recomputed from the raw postings whenever either
set of rules changes.

Agents read only `GateResult.cleaned_text`, never the raw posting.
"""

from dataclasses import dataclass
from typing import Any, Literal

from pipeline import posting_guard
from pipeline.alarm_triage import Tier, TriageRules, default_rules, triage

# Bump when the detection rules in posting_guard.py change.
DETECTION_VERSION = 1


def gate_version(rules: TriageRules | None = None) -> str:
    """Detection version + triage rules version, e.g. "d1-t1". Stored with every result, so we
    can tell which postings were judged by older rules and re-run the gate on them from raw."""
    return f"d{DETECTION_VERSION}-t{(rules or default_rules()).version}"


GATE_VERSION = gate_version()

Mode = Literal["html", "text", "auto"]
MODES: tuple[Mode, ...] = ("html", "text", "auto")


@dataclass(frozen=True)
class GateResult:
    cleaned_text: str  # visible text with hidden content and invisible characters removed
    findings: dict[str, Any]  # everything the gate found (hidden blocks, flagged lines, ...)
    verdict: str  # one-line summary, e.g. "posting_guard: clean"
    alarmed: bool  # True when a signal points at targeting; see is_alarmed
    triage: Tier  # clean / benign / review / block; see pipeline/alarm_triage.py
    triage_reasons: tuple[str, ...]  # why, in words a person can check
    gate_version: str = GATE_VERSION


def is_alarmed(findings: dict[str, Any]) -> bool:
    """The same signals that put a warning in posting_guard.verdict().

    Hidden blocks and hidden URLs alone are not alarms: nearly every real page hides
    navigation chrome. These signals point at text written for an agent instead.
    """
    return bool(
        findings.get("instruction_like")
        or findings.get("invisible_flagged")
        or (findings.get("invisible_chars") or {}).get("tag")
        or findings.get("invisible_text")
        or findings.get("homoglyph_runs")
    )


def run_gate(raw: str, mode: Mode = "auto", rules: TriageRules | None = None) -> GateResult:
    """Clean, scan and triage one posting.

    mode: "html" for HTML descriptions (Greenhouse, Lever, LinkedIn), "text" for plain
    text, "auto" to guess from the content. rules: triage rules to judge with (default: the
    rules file); the rules loop passes a proposed set to compare against the current one.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    rules = rules or default_rules()
    cleaned, findings = posting_guard.guard(raw, mode)
    alarmed = is_alarmed(findings)
    judged = triage(findings, cleaned, alarmed, rules)
    return GateResult(
        cleaned_text=cleaned,
        findings=findings,
        verdict=findings["verdict"],
        alarmed=alarmed,
        triage=judged.tier,
        triage_reasons=judged.reasons,
        gate_version=gate_version(rules),
    )
