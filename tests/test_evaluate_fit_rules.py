"""The clearance dealbreaker (decision #37) and the rules-loop command that evaluates it.
Pure code; no LLM. Scoring tests live in tests/test_fit_scoring.py."""

import copy
import tomllib
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from agents.evaluate_fit_rules import (
    CASES_FILE,
    PHRASE_CASES_FILE,
    Sample,
    _lost_requirements,
    _move_html,
    compare,
    every_nth,
    golden_problems,
    phrase_problems,
    review_page,
    sort_postings,
)
from agents.fit_scoring import (
    find_clearance,
    load_rules,
    load_vocabulary,
    match_skill,
    score_brief,
)
from agents.profile import load_profile
from pipeline.config import REPO_ROOT

SAMPLE = REPO_ROOT / "data" / "sample"
TODAY = date(2026, 11, 3)
PROFILE = load_profile(SAMPLE)
RULES = load_rules()
WITHOUT = replace(RULES, clearance=None, version=1)
VOCAB = load_vocabulary()
CASES = tomllib.loads(Path(CASES_FILE).read_text(encoding="utf-8"))["cases"]


def brief(title="Data Engineer"):
    return {
        "title": title,
        "company": "Acme",
        "url": "https://example.com/job",
        "must_haves": [{"skill": "SQL", "weight": "core", "exact_phrases": ["SQL"]}],
        "nice_to_haves": [],
        "archetype": "pipeline_de",
        "work_mode": "remote",
    }


def profile_with(**background):
    applicant = copy.deepcopy(PROFILE.applicant)
    applicant["background"].update(background)
    return replace(PROFILE, applicant=applicant)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["text"][:50])
def test_golden_cases_land_in_their_tier(case):
    hit = find_clearance(case["text"], RULES.clearance)
    assert (hit[0] if hit else "none") == case["tier"]


def test_golden_problems_names_a_wrong_tier(tmp_path):
    assert golden_problems(RULES.clearance) == []
    cases = tmp_path / "cases.toml"
    cases.write_text('cases = [{ text = "Active TS/SCI", tier = "none" }]', encoding="utf-8")
    assert golden_problems(RULES.clearance, cases) == ["want none, got hold: 'Active TS/SCI'"]


def test_rules_without_the_section_check_nothing():
    r = score_brief(brief("Data Engineer (TS/SCI)"), PROFILE, WITHOUT, VOCAB, TODAY)
    assert r.dealbreakers == []


def test_a_clearance_in_the_title_is_a_dealbreaker():
    r = score_brief(brief("Junior Data Engineer (TS/SCI)"), PROFILE, RULES, VOCAB, TODAY)
    assert r.decision == "skip"
    assert r.dealbreakers == [
        "clearance: the posting asks for one the profile doesn't have ('TS/SCI')"
    ]


def test_a_clearance_in_the_text_is_a_dealbreaker():
    r = score_brief(brief(), PROFILE, RULES, VOCAB, TODAY, "Must hold an active Secret clearance.")
    assert r.decision == "skip"
    assert r.dealbreakers[0].startswith("clearance:")


def test_a_job_with_no_clearance_wording_is_untouched():
    r = score_brief(brief(), PROFILE, RULES, VOCAB, TODAY, "Build pipelines. Family Medical Leave.")
    assert r.dealbreakers == []
    assert r.decision != "skip"


@pytest.mark.parametrize(
    "background, text, skipped",
    [
        ({"has_security_clearance": True}, "Active TS/SCI required", False),
        ({"has_security_clearance": True}, "Ability to obtain a Secret clearance", False),
        ({"can_obtain_security_clearance": True}, "Ability to obtain a Secret clearance", False),
        ({"can_obtain_security_clearance": True}, "Active TS/SCI required", True),
        ({}, "Ability to obtain a Secret clearance", True),
        ({}, "Active TS/SCI required", True),
    ],
)
def test_the_profile_decides(background, text, skipped):
    r = score_brief(brief(), profile_with(**background), RULES, VOCAB, TODAY, text)
    assert bool(r.dealbreakers) is skipped


def test_compare_lists_only_decisions_that_change():
    briefs = [
        (1, brief("Junior Data Engineer (TS/SCI)"), "Build pipelines"),
        (2, brief(), "Build pipelines"),
    ]
    before, after, moves = compare(briefs, PROFILE, WITHOUT, RULES, VOCAB, TODAY)
    assert sum(before.values()) == sum(after.values()) == 2
    assert after["skip"] == 1
    assert [move.posting_version_id for move in moves] == [1]
    assert moves[0].after["decision"] == "skip"


def test_sort_postings_sorts_into_tiers():
    rows = [
        (1, "a", "Data Engineer (TS/SCI)", "text"),
        (2, "b", "Data Engineer", "Ability to obtain a Secret clearance."),
        (3, "c", "Data Engineer", "Clearance Required: Public Trust"),
        (4, "d", "Data Engineer", "Spark and SQL"),
    ]
    counts, tiers = sort_postings(rows, RULES.clearance)
    assert counts == {"hold": 1, "obtain": 1, "mention": 1, "none": 1}
    assert [s.posting_version_id for s in tiers["mention"]] == [3]


def test_every_nth_is_an_even_repeatable_spread():
    items = [Sample(i, "c", "t", "w", "x") for i in range(100)]
    assert [s.posting_version_id for s in every_nth(items, 5)] == [0, 20, 40, 60, 80]
    assert every_nth(items[:3], 5) == items[:3]


def test_review_page_shows_source_text_and_escapes_it():
    hostile = "<script>alert(1)</script> Active TS/SCI required"
    moved = (1, brief("Data Engineer <b>x</b>"), hostile)
    before, after, moves = compare([moved], PROFILE, WITHOUT, RULES, VOCAB, TODAY)
    counts, tiers = sort_postings([(1, "acme", "Data Engineer", hostile)], RULES.clearance)
    page = review_page(moves, before, after, counts, tiers, WITHOUT, RULES)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert "<mark>TS/SCI</mark>" in page
    assert f"v1 → v{RULES.version}" in page


# ---------------------------------------------------------------- phrase matching (decision #42)

PHRASE_RULES = load_rules()
PHRASE_VOCAB = load_vocabulary()
PHRASE_CASES = tomllib.loads(Path(PHRASE_CASES_FILE).read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", PHRASE_CASES, ids=lambda c: f"{c['skill']}-{c['phrases']}"[:60])
def test_phrase_cases(case):
    item = {"skill": case["skill"], "exact_phrases": case["phrases"]}
    match = match_skill(item, PROFILE.bank, PHRASE_VOCAB, PHRASE_RULES.phrase_match)
    assert (match.skill is not None) == case["covered"]


def test_phrase_problems_names_a_wrong_case(tmp_path):
    assert phrase_problems(PHRASE_RULES, PHRASE_VOCAB, PROFILE) == []
    cases = tmp_path / "cases.toml"
    cases.write_text(
        'cases = [{ skill = "Java", phrases = ["Java"], covered = true }]', encoding="utf-8"
    )
    problems = phrase_problems(PHRASE_RULES, PHRASE_VOCAB, PROFILE, cases)
    assert problems == ["want covered=True: Java ['Java']"]


def test_the_current_any_part_rule_fails_the_cases_the_proposal_fixes():
    any_part = replace(PHRASE_RULES, phrase_match="any_part")
    problems = phrase_problems(any_part, PHRASE_VOCAB, PROFILE)
    assert any("Java & Python" in problem for problem in problems)


def test_an_unknown_phrase_setting_is_refused(tmp_path):
    text = (REPO_ROOT / "config" / "proposals" / "fit_scoring.v3.toml").read_text(encoding="utf-8")
    path = tmp_path / "rules.toml"
    path.write_text(text.replace('"alternatives_only"', '"whatever"'), encoding="utf-8")
    with pytest.raises(ValueError, match="exact_phrases"):
        load_rules(path)


def test_a_move_from_phrase_matching_names_what_was_lost_and_shows_the_posting():
    job = {
        **brief(),
        "must_haves": [
            {"skill": "SQL", "weight": "core", "exact_phrases": ["SQL"]},
            {"skill": "Java", "weight": "core", "exact_phrases": ["Java & Python"]},
        ],
    }
    old = replace(PHRASE_RULES, phrase_match="any_part", version=2)
    text = "<script>x</script> Java & Python"
    _, _, moves = compare([(1, job, text)], PROFILE, old, PHRASE_RULES, VOCAB, TODAY, True)
    assert _lost_requirements(moves[0]) == ["Java"]
    page = _move_html(moves[0])
    assert "Java &amp; Python" in page
    assert "<script>x" not in page


def test_compare_can_use_a_proposed_vocabulary():
    job = {
        **brief(),
        "must_haves": [
            {
                "skill": "Git/GitHub",
                "weight": "core",
                "exact_phrases": ["version control (GitHub)"],
            },
        ],
    }
    old_vocab = replace(
        PHRASE_VOCAB,
        synonyms={k: v for k, v in PHRASE_VOCAB.synonyms.items() if k != "git/github"},
    )
    _, _, moves = compare(
        [(1, job, "text")],
        PROFILE,
        PHRASE_RULES,
        PHRASE_RULES,
        old_vocab,
        TODAY,
        True,
        PHRASE_VOCAB,
    )
    assert moves[0].before["must_have_coverage"] == 0
    assert moves[0].after["must_have_coverage"] == 1
