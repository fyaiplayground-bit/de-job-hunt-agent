"""Sort every gate result into clean / benign / review / block, deterministically.

The gate (pipeline/posting_guard.py) says *whether* something looks aimed at an AI. Triage says
*what to do about it*, using the same checks a person would make, written down as rules:

  block   anything hidden: instruction words in hidden content, invisible text, tag characters,
          or invisible characters splitting words. Real attacks hide; honest text doesn't need to.
  review  visible but not clearly harmless: a strong instruction rule, a steering word ("rate",
          "candidate", a URL, ...), look-alike letters, or hidden URLs. A person looks.
  benign  visible, flagged only by weak rules (config/triage_rules.toml), no steering words, no
          other signal. Known false-positive shapes like "SSH" in a skill list.
  clean   the gate raised no alarm.

Same findings + same rules file -> same tier and reasons, every time. The rules change only
through the rules loop (decision #22).
"""

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pipeline import posting_guard

RULES_FILE = Path(__file__).resolve().parent.parent / "config" / "triage_rules.toml"

Tier = Literal["clean", "benign", "review", "block"]

# A stable name for each instruction pattern in posting_guard.INSTRUCTION_PATTERNS, found by a
# piece of text unique to that pattern's source. The rules file refers to these names, never to
# list positions. If upstream adds or changes a pattern, the test that every pattern has exactly
# one name fails, and the new pattern must be named (and is strong until we decide otherwise).
RULE_SIGNATURES: dict[str, str] = {
    "ignore_previous": r"\bignore (all|any",
    "disregard_previous": r"\b(disregard|forget)",
    "you_are_an_ai": r"\byou are (?:an?|the)",
    "system_prompt": r"\bsystem prompt\b",
    "dont_tell_user": r"(tell|inform) the user",
    "dont_reveal_to_user": r"(mention|reveal|disclose)",
    "run_the_following": r"\b(run|execute) the following",
    "as_an_ai": r"\bas an ai",
    "role_marker": r"(assistant|system|user)\s*:",
    "chat_template_token": r"<\|",
    "inst_token": r"\[INST\]",
    "markdown_system_heading": r"###\s*(system|instruction)",
    "network_tools": r"(curl|wget|ssh|scp)",
    "dotenv": r"\.env\b",
    "settings_json": r"settings\.json",
    "allowed_tools": r"allowed-tools",
    "tool_call": r"tool_use",
}


def _name_patterns() -> dict[str, re.Pattern[str]]:
    named = {}
    for name, signature in RULE_SIGNATURES.items():
        matches = [p for p in posting_guard.INSTRUCTION_PATTERNS if signature in p.pattern]
        if len(matches) != 1:
            raise RuntimeError(f"rule {name!r} matches {len(matches)} patterns; expected exactly 1")
        named[name] = matches[0]
    return named


NAMED_PATTERNS = _name_patterns()


@dataclass(frozen=True)
class TriageRules:
    version: int
    weak_rules: frozenset[str]
    steering_terms: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class Triage:
    tier: Tier
    reasons: tuple[str, ...]


def load_rules(path: Path = RULES_FILE) -> TriageRules:
    with path.open("rb") as f:
        raw = tomllib.load(f)
    unknown = set(raw["weak_rules"]) - set(NAMED_PATTERNS)
    if unknown:
        raise ValueError(f"{path.name}: unknown rule names in weak_rules: {sorted(unknown)}")
    return TriageRules(
        version=int(raw["version"]),
        weak_rules=frozenset(raw["weak_rules"]),
        steering_terms=tuple(re.compile(term, re.I) for term in raw["steering_terms"]),
    )


@lru_cache(maxsize=1)
def default_rules() -> TriageRules:
    return load_rules()


def rules_matching(line: str) -> list[str]:
    """Names of the instruction rules that fire on this line."""
    return [name for name, pattern in NAMED_PATTERNS.items() if pattern.search(line)]


def visible_line(excerpt: str, cleaned_text: str) -> str | None:
    """The full visible line an excerpt came from, or None if it isn't in the visible text.

    Excerpts are cut to 200 characters with an ellipsis; steering words are checked against the
    whole line so that nothing can hide after the cut.
    """
    core = excerpt.strip("…")
    for line in cleaned_text.splitlines():
        if core and core in line.strip():
            return line.strip()
    return None


def triage(
    findings: dict[str, Any], cleaned_text: str, alarmed: bool, rules: TriageRules | None = None
) -> Triage:
    rules = rules or default_rules()
    if not alarmed:
        return Triage("clean", ("no alarm",))

    # block: anything hidden
    blocks = []
    if (findings.get("invisible_chars") or {}).get("tag"):
        blocks.append("tag characters (text hidden from the reader)")
    if findings.get("invisible_text"):
        blocks.append("text spelled in invisible characters")
    if findings.get("invisible_flagged"):
        blocks.append("invisible characters inside words or bidi overrides")
    for block in findings.get("hidden_blocks") or []:
        if rules_matching(block):
            blocks.append(f"instruction rule in hidden content: {', '.join(rules_matching(block))}")
    visible_lines = {}
    for excerpt in findings.get("instruction_like") or []:
        line = visible_line(excerpt, cleaned_text)
        if line is None:
            blocks.append("instruction-like line that is not in the visible text")
        else:
            visible_lines[excerpt] = line
    if blocks:
        return Triage("block", tuple(blocks))

    # review: visible but not clearly harmless
    reviews = []
    if findings.get("homoglyph_runs"):
        reviews.append(f"look-alike letters in: {', '.join(findings['homoglyph_runs'][:3])}")
    if findings.get("hidden_urls"):
        reviews.append("URL only in hidden content")
    benign_reasons = []
    for line in visible_lines.values():
        fired = rules_matching(line)
        strong = [name for name in fired if name not in rules.weak_rules]
        steering = [m.group(0) for p in rules.steering_terms if (m := p.search(line))]
        if strong:
            reviews.append(f"strong rule {', '.join(strong)}: {line[:120]}")
        elif steering:
            reviews.append(f"weak rule with steering words {steering[:3]}: {line[:120]}")
        else:
            benign_reasons.append(
                f"only weak rule {', '.join(fired)}, no steering words: {line[:120]}"
            )
    if reviews:
        return Triage("review", tuple(reviews))
    if not benign_reasons:  # alarmed with nothing explaining it: let a person look
        return Triage("review", ("alarm with no visible flagged line",))
    return Triage("benign", (*benign_reasons, f"rules v{rules.version}"))
