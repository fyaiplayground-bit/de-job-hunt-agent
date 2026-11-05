"""Code checks on a tailored resume's content (decision #38). No LLM: the same draft always gets
the same answer.

    facts    must hold or the resume can't go out: evidence, numbers, skills with no entry
    quality  sent back for revision: keywords in the JD's wording, recruiter habits

The draft is what the LLM wrote: headline, summary, bullets with the evidence they cite, skills.
"""

import re
from dataclasses import dataclass
from typing import Any

from agents.fit_scoring import Vocabulary, _resolve, _split
from agents.profile import EvidenceBank, Profile, _numbers, check_resume

MIN_KEYWORD_COVERAGE = 0.8
MIN_NUMBERED_BULLETS = 0.5
MAX_BULLET_CHARS = 220  # about two lines on the page
BANNED_OPENINGS = ("responsible for", "worked on", "helped")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#]*")
FIRST_PERSON = re.compile(r"\bI\b|\b[Mm]y\b")
# Advertises a gap (FL, 2026-11-04). Only the headline and summary: a bullet may describe a
# system "moving to" somewhere.
TRANSITION = re.compile(
    r"\b(moving|moved|transitioning|transitioned|pivoting|shifting)\s+(in)?to\b"
    r"|\btransition\s+(in)?to\b|\baspiring\b|\bcareer\s+(change|switch|transition)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Problems:
    facts: tuple[str, ...]
    quality: tuple[str, ...]

    @property
    def all(self) -> list[str]:
        return [*self.facts, *self.quality]


def mentions(text: str, term: str) -> bool:
    """The whole term appears in the text, ignoring case. Very short terms must match case too,
    so the language "Go" isn't found in "go-live"."""
    flags = 0 if len(term) <= 3 else re.IGNORECASE
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags) is not None


def draft_bullets(draft: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(section, role or project id, bullet) for every bullet."""
    return [
        (section, entry["where"], bullet)
        for section in ("experience", "projects")
        for entry in draft[section]
        for bullet in entry["bullets"]
    ]


def draft_text(draft: dict[str, Any]) -> str:
    """Everything the LLM wrote that reaches the page."""
    bullets = [bullet["text"] for _, _, bullet in draft_bullets(draft)]
    return "\n".join([draft["headline"], draft["summary"], *bullets, *draft["skills"]])


def check_bullets(draft: dict[str, Any], bank: EvidenceBank) -> list[str]:
    """Each bullet cites real evidence of its own role or project, and its numbers are in the
    metrics of what it cites. Stricter than `check_resume`, which reads the whole bank."""
    problems = []
    entries = {entry.id: entry for entry in bank.evidence}
    places = {
        "experience": {role.id for role in bank.roles},
        "projects": {project.id for project in bank.projects},
    }
    for section, where, bullet in draft_bullets(draft):
        text = bullet["text"]
        if where not in places[section]:
            problems.append(f"{section}: {where!r} is not in the Evidence Bank: {text!r}")
            continue
        if not bullet["evidence"]:
            problems.append(f"bullet cites no evidence: {text!r}")
            continue
        allowed: set[str] = set()
        for evidence_id in bullet["evidence"]:
            entry = entries.get(evidence_id)
            if entry is None:
                problems.append(f"bullet cites unknown evidence {evidence_id!r}: {text!r}")
            elif entry.where != where:
                problems.append(f"evidence {evidence_id!r} belongs to {entry.where!r}: {text!r}")
            else:
                allowed |= set().union(*map(_numbers, entry.metrics), set())
        for number in sorted(_numbers(text) - allowed):
            problems.append(f"the number {number} is not in the cited evidence: {text!r}")
    return problems


def _bank_text(bank: EvidenceBank) -> str:
    parts = [text for e in bank.evidence for text in (e.summary, *e.skills, *e.metrics)]
    parts += [text for s in bank.skills for text in (s.name, *s.aliases)]
    parts += [text for r in bank.roles for text in (r.title, r.employer, r.location)]
    parts += [text for p in bank.projects for text in (p.name, p.description)]
    return "\n".join(parts)


def _phrases(brief: dict[str, Any], names: list[str]) -> list[str]:
    """The posting's own wording for these skills: "Apache Kafka" also goes by "Kafka"."""
    items = [*brief["must_haves"], *brief["nice_to_haves"]]
    return [p for item in items if item["skill"] in names for p in item.get("exact_phrases", [])]


def _words(text: str) -> set[str]:
    return {word.lower() for word in WORD.findall(text)}


def _unbacked_alternatives(
    brief: dict[str, Any], bank: EvidenceBank, vocab: Vocabulary
) -> list[str]:
    """In an either/or entry, Python covers "Python or Java", but that gives no right to say Java:
    the parts the profile doesn't have, wherever the entry was marked covered."""
    terms = []
    for item in (*brief["must_haves"], *brief["nice_to_haves"]):
        if " or " not in item["skill"]:
            continue
        for name in (item["skill"], *item.get("exact_phrases", [])):
            terms += [
                part for part in _split(name)
                if " or " not in part and not _resolve(part, bank, vocab)[0]
            ]
    return terms


def check_no_invented_skills(
    draft: dict[str, Any],
    brief: dict[str, Any],
    fit: dict[str, Any],
    bank: EvidenceBank,
    vocab: Vocabulary,
) -> list[str]:
    """Nothing the job asks for that the profile lacks, and no tool the vocabulary knows but the
    profile doesn't, may appear on the page. Words the Evidence Bank itself uses are fine."""
    text, facts = draft_text(draft), _bank_text(bank)
    missing = [*fit["not_covered"], *fit["nice_missing"]]
    terms = [term for name in (*missing, *_phrases(brief, missing)) for term in _split(name)]
    terms += [member for members in vocab.families.values() for member in members]
    terms += _unbacked_alternatives(brief, bank, vocab)
    fact_words = _words(facts)
    found = []
    for term in dict.fromkeys(terms):
        if not mentions(text, term) or mentions(facts, term):
            continue
        if _words(term) <= fact_words:  # "dbt tests": dbt and tests are both in the bank
            continue
        if not _resolve(term, bank, vocab)[0]:
            found.append(f"names {term!r}, which has no Evidence Bank entry")
    return found


def check_no_unknown_names(
    draft: dict[str, Any],
    brief: dict[str, Any],
    fit: dict[str, Any],
    bank: EvidenceBank,
    vocab: Vocabulary,
) -> list[str]:
    """A capitalized word mid-sentence is usually a product name. It must come from the Evidence
    Bank, the vocabulary's wordings, or the job's wording for a skill the profile covers. This
    catches a tool nobody listed, such as a draft that adds "Terraform" on its own."""
    covered = [
        m["asked"] for m in (*fit["covered"], *fit["nice_covered"]) if " or " not in m["asked"]
    ]
    allowed = _words(_bank_text(bank))
    allowed |= _words(" ".join([*vocab.synonyms, *vocab.families, *covered]))
    allowed |= _words(" ".join(_phrases(brief, covered)))
    sentences = [draft["summary"], *(bullet["text"] for _, _, bullet in draft_bullets(draft))]
    found: dict[str, None] = {}
    for sentence in sentences:
        for match in WORD.finditer(sentence):
            word = match[0]
            starts_sentence = sentence[: match.start()].rstrip()[-1:] in ("", ".", ";", ":")
            if starts_sentence or word == "I" or word.lower() in allowed:
                continue
            if any(c.isupper() for c in word):
                found[word] = None
    return [f"names {word!r}, which isn't in the Evidence Bank" for word in found]


def known_skill(bank: EvidenceBank, vocab: Vocabulary):
    """A Skills item may be any wording that leads to a skill in the profile, the JD's included."""
    return lambda item: bool(_resolve(item.strip(), bank, vocab)[0])


def check_facts(
    draft: dict[str, Any],
    resume: str,
    profile: Profile,
    brief: dict[str, Any],
    fit: dict[str, Any],
    vocab: Vocabulary,
) -> list[str]:
    bank = profile.bank
    problems = check_bullets(draft, bank)
    problems += check_no_invented_skills(draft, brief, fit, bank, vocab)
    problems += check_no_unknown_names(draft, brief, fit, bank, vocab)
    problems += check_resume(resume, bank, profile.applicant, known_skill(bank, vocab))
    allowed = set().union(*(_numbers(m) for entry in bank.evidence for m in entry.metrics))
    for number in sorted(_numbers(draft["headline"]) - allowed):
        problems.append(f"the number {number} in the headline is in no Evidence Bank metric")
    return problems


def keyword_coverage(
    draft: dict[str, Any], brief: dict[str, Any], fit: dict[str, Any]
) -> tuple[float, list[str]]:
    """Share of the must-haves the profile covers that the page says, by name or in the posting's
    wording, and the ones it doesn't say. 1.0 when the profile covers none."""
    text = draft_text(draft)
    items = {item["skill"]: item for item in brief["must_haves"]}
    missing = []
    covered = fit["covered"]
    for match in covered:
        item = items.get(match["asked"], {})
        forms = [match["asked"], match["skill"], *item.get("exact_phrases", [])]
        if not any(mentions(text, form) for form in forms if form):
            missing.append(match["asked"])
    return (1 - len(missing) / len(covered) if covered else 1.0), missing


def check_quality(draft: dict[str, Any], brief: dict[str, Any], fit: dict[str, Any]) -> list[str]:
    problems = []
    share, missing = keyword_coverage(draft, brief, fit)
    if share < MIN_KEYWORD_COVERAGE:
        problems.append(
            f"only {share:.0%} of the covered must-haves are on the page "
            f"(need {MIN_KEYWORD_COVERAGE:.0%}); missing: {', '.join(missing)}"
        )
    if not mentions(draft["headline"], "engineer"):
        problems.append(f"the headline doesn't name a target role: {draft['headline']!r}")
    bullets = [bullet["text"] for _, _, bullet in draft_bullets(draft)]
    if not bullets:
        problems.append("the resume has no bullets")
    numbered = sum(bool(_numbers(text)) for text in bullets)
    if bullets and numbered / len(bullets) < MIN_NUMBERED_BULLETS:
        problems.append(f"only {numbered} of {len(bullets)} bullets carry a number")
    for text in (draft["headline"], draft["summary"]):
        if TRANSITION.search(text):
            problems.append(f"transition wording advertises a gap: {text!r}")
    for text in [draft["summary"], *bullets]:
        if FIRST_PERSON.search(text):
            problems.append(f"written in the first person: {text!r}")
    for text in bullets:
        if text.lower().startswith(BANNED_OPENINGS):
            problems.append(f"bullet opens weakly: {text!r}")
        if len(text) > MAX_BULLET_CHARS:
            problems.append(f"bullet is over {MAX_BULLET_CHARS} characters: {text!r}")
    if not any(entry["bullets"] for entry in draft["projects"]):
        problems.append("no project on the resume: projects carry the DE work outside the day job")
    return problems


def check_draft(
    draft: dict[str, Any],
    resume: str,
    profile: Profile,
    brief: dict[str, Any],
    fit: dict[str, Any],
    vocab: Vocabulary,
) -> Problems:
    return Problems(
        facts=tuple(check_facts(draft, resume, profile, brief, fit, vocab)),
        quality=tuple(check_quality(draft, brief, fit)),
    )
