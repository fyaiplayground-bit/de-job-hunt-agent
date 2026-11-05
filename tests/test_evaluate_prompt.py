"""Tests for agents/evaluate_prompt.py and the jd-analysis golden set (decision #32)."""

import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agents.evaluate_prompt import (
    GOLDEN_FILE,
    GoldenCase,
    Totals,
    compare,
    evaluate,
    load_golden,
    normalize,
    score_case,
)
from agents.jd_analysis import BRIEF_SCHEMA
from agents.llm import FakeClient
from agents.skills import load_skill, parse_skill
from pipeline.config import REPO_ROOT, LlmSettings
from pipeline.gate_step import gate_pending
from pipeline.load import load_jobs

SETTINGS = LlmSettings(model="claude-opus-5-5", effort="medium")
CASE = GoldenCase(
    name="demo", source="greenhouse", source_job_id="1", content_hash="x", why="",
    must_haves=(("SQL",), ("Apache Airflow", "Airflow"), ("dbt",), ("CI/CD",)),
    archetype=("pipeline_de",), work_mode="remote", years_required=(3,),
)


def _brief(**changes):
    brief = {
        "archetype": "pipeline_de", "seniority": "mid", "years_required": 3,
        "must_haves": [
            {"skill": "SQL", "exact_phrases": ["SQL"], "weight": "core"},
            {"skill": "Workflow orchestration", "exact_phrases": ["Airflow"], "weight": "normal"},
            {"skill": "CI/CD pipelines", "exact_phrases": ["CI/CD"], "weight": "normal"},
            {"skill": "Kubernetes", "exact_phrases": ["Kubernetes"], "weight": "normal"},
        ],
        "nice_to_haves": [{"skill": "dbt", "exact_phrases": ["dbt"]}],
        "work_mode": "remote", "locations": [], "remote_regions": [],
        "salary": {"min": None, "max": None, "currency": None}, "sponsorship": "unstated",
        "hidden_signals": [], "knockout_questions_likely": [], "safety_flags": [],
    }
    brief.update(changes)
    return brief


# ---------------------------------------------------------------- the golden file


def test_golden_set_is_well_formed_and_holds_no_posting_text():
    cases = load_golden()
    assert len(cases) == 13
    assert len({c.name for c in cases}) == 13
    enums = BRIEF_SCHEMA["properties"]
    for case in cases:
        assert case.source in {"greenhouse", "lever", "freehire"}
        assert len(case.content_hash) == 64
        assert set(case.archetype) <= set(enums["archetype"]["enum"]), case.name
        assert case.work_mode in enums["work_mode"]["enum"], case.name
        assert all(isinstance(y, int) for y in case.years_required), case.name
    # public repo: identifiers and expected values only, never a description
    raw = tomllib.loads(GOLDEN_FILE.read_text(encoding="utf-8"))["case"]
    allowed = {"name", "source", "source_job_id", "content_hash", "why", "must_haves",
               "archetype", "work_mode", "years_required", "nice_to_haves", "one_entry",
               "not_must_haves"}
    assert all(set(c) <= allowed for c in raw)
    assert all(len(c["why"]) < 120 for c in raw)


def test_v3_proposal_differs_from_v2_only_in_the_years_rule():
    current = load_skill("jd-analysis")
    proposal_path = REPO_ROOT / "config" / "proposals" / "jd-analysis.v3.md"
    proposal = parse_skill(proposal_path.read_text(encoding="utf-8"), "v3")
    assert (proposal.name, proposal.version) == ("jd-analysis", 3)
    if current.version >= 3:  # adopted, and later versions may have moved on
        return
    changed = set(proposal.body.splitlines()) ^ set(current.body.splitlines())
    assert all("years" in line.lower() or line.startswith("6. **Seniority**") for line in changed)


# ---------------------------------------------------------------- scoring


def test_normalize():
    assert normalize("CI/CD") == "ci cd"
    assert normalize("  Apache   Airflow ") == "apache airflow"
    assert normalize("C++ and C#") == "c++ and c#"


def test_score_matches_names_and_exact_phrases():
    score = score_case(CASE, _brief())
    assert (score.expected, score.hits) == (4, 3)  # SQL, Airflow (via phrase), CI/CD (via phrase)
    assert score.missed == ("dbt",)
    assert score.misplaced == ("dbt",)  # it was listed, as a nice-to-have
    assert (score.predicted, score.matched_predicted) == (4, 3)  # Kubernetes isn't labeled
    assert (score.archetype_ok, score.work_mode_ok, score.years_ok) == (True, True, True)


def test_score_years_archetype_and_unscored_cases():
    assert score_case(CASE, _brief(years_required=5)).years_ok is False
    assert score_case(CASE, _brief(archetype="infra_de")).archetype_ok is False
    empty = GoldenCase("empty", "freehire", "2", "y", "", (), (), "unclear", ())
    score = score_case(empty, _brief(must_haves=[], years_required=None, work_mode="unclear"))
    assert (score.expected, score.hits, score.archetype_ok, score.years_ok) == (0, 0, None, True)
    assert score_case(empty, _brief(years_required=2)).years_ok is False


def test_nice_to_haves_kept_lost_and_promoted():
    case = replace(CASE, nice_to_haves=(("dbt",), ("Kubernetes", "K8s"), ("Terraform",)))
    score = score_case(case, _brief())
    assert (score.nice_expected, score.nice_kept) == (3, 2)  # dbt (nice), Kubernetes (must)
    assert score.nice_lost == ("Terraform",)
    assert score.promoted == ("Kubernetes",)  # listed only as a must-have


def test_golden_labels_never_list_one_skill_as_both_must_and_nice():
    for case in load_golden():
        must = {normalize(a) for alts in case.must_haves for a in alts}
        nice = {normalize(a) for alts in case.nice_to_haves for a in alts}
        assert must.isdisjoint(nice), (case.name, must & nice)


def test_review_page_escapes_posting_text_and_marks_skills():
    from agents.evaluate_prompt import Evaluation, review_page
    from agents.jd_analysis import Candidate

    case = replace(CASE, nice_to_haves=(("Terraform",),))
    text = "Must know SQL and Airflow. <script>alert(1)</script> Terraform is a plus."
    ev = Evaluation(label="demo@1")
    ev.candidates["demo"] = Candidate(1, "greenhouse", "Acme", "DE", "", "https://e.x/1", text)
    ev.briefs["demo"] = _brief()
    ev.scores.append(score_case(case, _brief()))
    page = review_page([case], ev)
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<mark>SQL</mark>" in page
    assert '<mark class="nice">Terraform</mark>' in page
    assert "✗ dbt" in page  # the missed must-have is shown as missed


def test_compare_allows_one_must_have_of_noise_and_nothing_else():
    current = Totals(hits=50, expected=60, archetype_ok=8, work_mode_ok=9, years_ok=6)
    assert compare(current, Totals(hits=49, expected=60, archetype_ok=8, work_mode_ok=9,
                                   years_ok=9)) == []
    problems = compare(current, Totals(hits=48, expected=60, archetype_ok=7, work_mode_ok=9,
                                       years_ok=6, failed=1))
    assert problems == [
        "must-haves found 48 < 50 (tolerance 1)",
        "archetype right 7 < 8",
        "1 cases failed (current: 0)",
    ]
    nice = compare(Totals(nice_kept=20, promoted=1), Totals(nice_kept=18, promoted=3))
    assert nice == [
        "nice-to-haves kept 18 < 20 (tolerance 1)",
        "nice-to-haves promoted to must 3 > 1 (tolerance 1)",
    ]


# ---------------------------------------------------------------- with the test database


@pytest.mark.db
def test_evaluate_finds_golden_postings_by_identity_and_writes_no_briefs(db, greenhouse_jobs):
    run_id = uuid4()
    db.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')", (run_id,),
    )
    load_jobs(db, "greenhouse", "example", greenhouse_jobs[:1], run_id, datetime.now(UTC))
    gate_pending(db)
    source_job_id, content_hash = db.execute(
        "select source_job_id, content_hash from raw.job_postings"
    ).fetchone()
    case = GoldenCase("fixture", "greenhouse", source_job_id, content_hash, "", (("SQL",),),
                      ("pipeline_de",), "remote", (3,))
    gone = GoldenCase("gone", "greenhouse", "999", "z" * 64, "", (), (), "unclear", ())

    client = FakeClient(_brief())
    result = evaluate(db, client, SETTINGS, load_skill("jd-analysis"), [case, gone])
    assert result.missing == ["gone"]
    assert [s.hits for s in result.scores] == [1]
    assert result.cost_usd == pytest.approx(0.008)
    assert client.requests[0].user.startswith("<data>\nCompany: Example Data Co\nTitle: ")
    assert db.execute("select count(*) from agents.jd_briefs").fetchone()[0] == 0

    again = evaluate(db, client, SETTINGS, load_skill("jd-analysis"), [case])
    assert again.cost_usd == 0 and len(client.requests) == 1  # answered from the cache


# ---------------------------------------------------------------- either/or and job functions


def _either_or_case():
    return replace(
        load_golden()[0],
        must_haves=(("Python",),),
        nice_to_haves=(),
        one_entry=((("Python",), ("Java",), ("Scala",)),),
        not_must_haves=("BI development",),
    )


def _entry(skill, *phrases):
    return {"skill": skill, "exact_phrases": list(phrases), "weight": "normal"}


def test_an_either_or_group_in_one_entry_is_kept():
    brief = _brief(must_haves=[_entry("Python or Java or Scala", "Python", "Java", "Scala")])
    score = score_case(_either_or_case(), brief)
    assert (score.groups_kept, score.groups_total) == (1, 1)


def test_an_either_or_group_across_entries_is_split():
    brief = _brief(must_haves=[_entry("Python", "Python"), _entry("Java", "Java")])
    score = score_case(_either_or_case(), brief)
    assert (score.groups_kept, score.groups_total) == (0, 1)


def test_a_job_function_listed_as_a_skill_is_counted():
    brief = _brief(must_haves=[_entry("Python"), _entry("BI development", "BI development")])
    assert score_case(_either_or_case(), brief).functions_listed == ("BI development",)


def test_compare_rejects_a_worse_reading_of_either_or_lines():
    current = Totals(groups_kept=3, groups_total=3, functions_listed=0)
    problems = compare(current, Totals(groups_kept=2, groups_total=3, functions_listed=1))
    assert any("either/or" in problem for problem in problems)
    assert any("job functions" in problem for problem in problems)


def test_v4_proposal_only_adds_the_two_rules():
    current = load_skill("jd-analysis")
    proposal_path = REPO_ROOT / "config" / "proposals" / "jd-analysis.v4.md"
    proposal = parse_skill(proposal_path.read_text(encoding="utf-8"), "v4")
    assert (proposal.name, proposal.version) == ("jd-analysis", 4)
    if current.version == 4:  # adopted: the skill file is the proposal
        assert current.body == proposal.body
        return
    added = set(proposal.body.splitlines()) - set(current.body.splitlines())
    assert all("Alternatives are one entry" in x or "Background is not a skill" in x for x in added)
    assert not set(current.body.splitlines()) - set(proposal.body.splitlines())
