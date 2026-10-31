"""JD safety gate: every job posting passes through `run_gate()` before any agent reads it.

The detection rules live in `pipeline/posting_guard.py` (copied from ai-job-search). This
module is our interface to them: one function in, one result object out, plus a version
number so results can be recomputed from the raw postings whenever the rules change.

Agents read only `GateResult.cleaned_text`, never the raw posting.
"""

from dataclasses import dataclass
from typing import Any, Literal

from pipeline import posting_guard

# Bump when the rules in posting_guard.py change. Stored with every result, so we can tell
# which postings were checked by an older version and re-run the gate on them from raw.
GATE_VERSION = "1"

Mode = Literal["html", "text", "auto"]
MODES: tuple[Mode, ...] = ("html", "text", "auto")


@dataclass(frozen=True)
class GateResult:
    cleaned_text: str  # visible text with hidden content and invisible characters removed
    findings: dict[str, Any]  # everything the gate found (hidden blocks, flagged lines, ...)
    verdict: str  # one-line summary, e.g. "posting_guard: clean"
    alarmed: bool  # True when a signal points at targeting; see _is_alarmed
    gate_version: str = GATE_VERSION


def _is_alarmed(findings: dict[str, Any]) -> bool:
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


def run_gate(raw: str, mode: Mode = "auto") -> GateResult:
    """Clean and scan one posting.

    mode: "html" for HTML descriptions (Greenhouse, Lever, LinkedIn), "text" for plain
    text, "auto" to guess from the content.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    cleaned, findings = posting_guard.guard(raw, mode)
    return GateResult(
        cleaned_text=cleaned,
        findings=findings,
        verdict=findings["verdict"],
        alarmed=_is_alarmed(findings),
    )
