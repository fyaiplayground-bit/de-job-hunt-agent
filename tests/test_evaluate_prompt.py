"""Tests for agents/evaluate_prompt.py and the jd-analysis golden set (decision #32)."""

import tomllib
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
    assert len(cases) == 10
    assert len({c.name for c in cases}) == 10
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
               "archetype", "work_mode", "years_required"}
    assert all(set(c) == allowed for c in raw)
    assert all(len(c["why"]) < 120 for c in raw)


def test_v3_proposal_differs_from_v2_only_in_the_years_rule():
    current = load_skill("jd-analysis")
    proposal_path = REPO_ROOT / "config" / "proposals" / "jd-analysis.v3.md"
    proposal = parse_skill(proposal_path.read_text(encoding="utf-8"), "v3")
    assert (proposal.name, proposal.version) == ("jd-analysis", 3)
    if current.version == 3:  # adopted: the skill file is the proposal
        assert current.body == proposal.body
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
