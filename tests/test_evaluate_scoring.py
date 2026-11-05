"""Tests for agents/evaluate_scoring.py, the vocabulary v2 wordings and brief_postings."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from agents.evaluate_scoring import JobChange, compare_vocabularies, review_page
from agents.fit_scoring import load_rules, load_vocabulary, score_brief
from agents.jd_analysis import brief_postings
from agents.llm import FakeClient
from agents.profile import load_profile
from agents.skills import load_skill
from pipeline.config import REPO_ROOT, LlmSettings

PROFILE = load_profile(REPO_ROOT / "data" / "sample")
RULES = load_rules()
PROPOSED = load_vocabulary()
V2_WORDINGS = {
    "bi development", "business intelligence", "sql performance tuning", "sql tuning",
    "query optimization", "query tuning", "query performance tuning",
}
# The vocabulary as it was before v2, to show what those wordings move.
CURRENT = replace(
    PROPOSED, synonyms={k: v for k, v in PROPOSED.synonyms.items() if k not in V2_WORDINGS}
)
TODAY = date(2026, 11, 4)


def brief(*skills, **changes):
    return {
        "company": "Acme",
        "title": "Data <b>Engineer</b>",
        "url": "https://example.com/job",
        "archetype": "pipeline_de",
        "work_mode": "remote",
        "nice_to_haves": [],
        "must_haves": [
            {"skill": skill, "weight": "normal", "exact_phrases": [skill]} for skill in skills
        ],
        **changes,
    }


@pytest.mark.parametrize(
    "wording", ["BI development", "Query optimization", "SQL performance tuning"]
)
def test_the_vocabulary_covers_these_wordings(wording):
    job = brief(wording)
    assert score_brief(job, PROFILE, RULES, CURRENT, TODAY).not_covered == [wording]
    assert score_brief(job, PROFILE, RULES, PROPOSED, TODAY).not_covered == []


def test_either_or_is_covered_by_one_part_only_when_the_name_says_so():
    split = brief("dbt", "Snowflake", "BigQuery")
    joined = brief("dbt or Snowflake or BigQuery")
    assert score_brief(split, PROFILE, RULES, PROPOSED, TODAY).must_have_coverage == pytest.approx(
        1 / 3
    )
    assert score_brief(joined, PROFILE, RULES, PROPOSED, TODAY).must_have_coverage == 1


def test_compare_vocabularies_lists_what_moves():
    rows = [(1, brief("SQL", "BI development"), ""), (2, brief("SQL"), "")]
    before, after, moved = compare_vocabularies(rows, PROFILE, RULES, CURRENT, PROPOSED, TODAY)
    assert sum(before.values()) == sum(after.values()) == 2
    assert [item[0] for item in moved] == [1]


def test_review_page_shows_the_posting_and_escapes_it():
    old, new = brief("Snowflake", "dbt"), brief("dbt or Snowflake")
    change = JobChange(
        7,
        old,
        new,
        "<script>alert(1)</script> dbt or Snowflake",
        score_brief(old, PROFILE, RULES, CURRENT, TODAY),
        score_brief(new, PROFILE, RULES, PROPOSED, TODAY),
    )
    page = review_page([change], {"apply": 1}, {"apply": 1}, [])
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert "<b>Engineer</b>" not in page
    assert "dbt or Snowflake" in page


@pytest.mark.db
def test_brief_postings_answers_without_storing_a_brief(db, greenhouse_jobs):
    from pipeline.gate_step import gate_pending
    from pipeline.load import load_jobs

    run_id = uuid4()
    db.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')",
        (run_id,),
    )
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, run_id, datetime.now(UTC))
    gate_pending(db)
    posting = db.execute("select min(posting_version_id) from raw.job_postings").fetchone()[0]
    answer = {"must_haves": [], "nice_to_haves": [], "archetype": "pipeline_de"}
    client = FakeClient(answer=answer)
    settings = LlmSettings(model="claude-opus-5-5", effort="medium")
    # A fake schema check would refuse a partial answer, so answer every required field.
    from agents.jd_analysis import BRIEF_SCHEMA

    client.answer = {key: answer.get(key) for key in BRIEF_SCHEMA["required"]}
    briefs, paid = brief_postings(db, client, settings, load_skill("jd-analysis"), [posting])
    assert set(briefs) == {posting}
    assert paid > 0
    assert briefs[posting][0]["company"]  # code adds the board's facts
    assert db.execute("select count(*) from agents.jd_briefs").fetchone()[0] == 0
