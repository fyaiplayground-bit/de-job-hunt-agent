"""Tests for agents/fit_scoring.py against the fictional sample profile (decision #35): skill
matching, the score, dealbreakers, decisions, and stored scores. Pure code; no LLM anywhere."""

import copy
import json
import shutil
from dataclasses import replace
from datetime import date

import pytest

from agents.fit_scoring import (
    candidate_years,
    load_rules,
    load_vocabulary,
    match_skill,
    profile_fingerprint,
    run,
    score_brief,
)
from agents.profile import load_profile
from pipeline.config import REPO_ROOT

SAMPLE = REPO_ROOT / "data" / "sample"
TODAY = date(2026, 11, 2)
PROFILE = load_profile(SAMPLE)
RULES = load_rules()
VOCAB = load_vocabulary()


def item(skill, phrases=(), weight="normal"):
    return {"skill": skill, "exact_phrases": list(phrases), "weight": weight}


def brief(must, nice=(), **changes):
    base = {
        "company": "Acme", "title": "Data Engineer", "url": "https://example.com/1",
        "board_location": "Remote - US", "archetype": "pipeline_de", "seniority": "mid",
        "years_required": 3, "must_haves": list(must), "nice_to_haves": list(nice),
        "work_mode": "remote", "locations": [], "remote_regions": [],
        "salary": {"min": None, "max": None, "currency": None}, "sponsorship": "unstated",
        "hidden_signals": [], "knockout_questions_likely": [], "safety_flags": [],
    }
    base.update(changes)
    return base


def matched(skill, phrases=()):
    m = match_skill(item(skill, phrases), PROFILE.bank, VOCAB)
    return m.skill, m.via


# ---------------------------------------------------------------- matching


def test_skill_matching_routes():
    assert matched("SQL") == ("SQL", "name")
    assert matched("Airflow") == ("Apache Airflow", "alias")
    assert matched("ETL/ELT pipelines") == ("ETL", "synonym")
    assert matched("AWS") == ("Amazon Redshift", "family")  # strongest member, production
    assert matched("Amazon Web Services") == ("Amazon Redshift", "family")  # synonym -> family
    assert matched("Cloud SQL / PostgreSQL") == ("PostgreSQL", "name")  # part of the name
    assert matched("Monitoring and data quality") == ("Data quality", "name")
    assert matched("Kafka") == (None, "")


def test_exact_phrases_never_match_through_a_family():
    """A brief may quote "cloud data warehouse" next to Snowflake; that mustn't cover Snowflake."""
    assert matched("Snowflake", ["Snowflake", "cloud data warehouse"]) == (None, "")
    assert matched("Data pipelines engineering", ["ETL"]) == ("ETL", "name")  # direct is fine


def test_family_level_is_the_strongest_member():
    m = match_skill(item("Orchestration"), PROFILE.bank, VOCAB)
    assert (m.skill, m.level) == ("Apache Airflow", "practiced")  # the only orchestrator Alex has


def test_candidate_years_count_every_role():
    # analyst 2017-06..2021-02 (45 months) + BIE 2021-03..2026-11 (69 months) = 9.5 years
    assert candidate_years(PROFILE.bank, TODAY) == 9.5


# ---------------------------------------------------------------- score and decision


def test_score_formula_and_referral():
    b = brief(
        must=[item("SQL", weight="core"), item("Python"), item("Kafka")],
        nice=[item("dbt"), item("Scala")], archetype="analytics_engineer",
    )
    r = score_brief(b, PROFILE, RULES, VOCAB, TODAY)
    assert r.must_have_coverage == 0.75  # (2 + 1) of (2 + 1 + 1): core counts double
    assert r.nice_coverage == 0.5
    assert r.score == 68  # 70 x 0.75 + 20 x 0.5 + 5 = 67.5
    assert r.decision == "apply_referral"
    assert r.not_covered == ["Kafka"] and r.nice_missing == ["Scala"]
    assert r.lead_with == ["SQL", "Python"]  # core first


def test_no_nice_to_haves_count_as_well_covered_as_the_must_haves():
    r = score_brief(brief([item("SQL"), item("Kafka")]), PROFILE, RULES, VOCAB, TODAY)
    assert r.nice_coverage == r.must_have_coverage == 0.5
    assert (r.score, r.decision) == (45, "apply")  # 35 + 10; exactly at the 50% bar


def test_below_the_bar_is_skipped_with_the_missing_skills():
    r = score_brief(brief([item("SQL"), item("Kafka"), item("Scala")]), PROFILE, RULES, VOCAB,
                    TODAY)
    assert r.decision == "skip" and r.not_covered == ["Kafka", "Scala"]


def test_a_brief_without_must_haves_is_skipped():
    r = score_brief(brief([]), PROFILE, RULES, VOCAB, TODAY)
    assert (r.decision, r.score, r.must_have_coverage) == ("skip", 0, None)
    assert r.dealbreakers == ["brief lists no must-haves (posting text too thin to judge)"]


@pytest.mark.parametrize(
    ("changes", "dealbreaker"),
    [
        ({"years_required": 11}, "years: asks 11, profile has 9.5"),
        ({"years_required": 10}, None),  # within the one-year tolerance
        ({"salary": {"min": 90000, "max": 110000, "currency": "USD"}},
         "salary: top of range 110,000 is below the floor 120,000"),
        ({"salary": {"min": 60, "max": 70, "currency": "USD"}}, None),  # hourly: not compared
        ({"salary": {"min": 100000, "max": None, "currency": "EUR"}}, None),  # other currency
        ({"sponsorship": "not_available"}, None),  # the sample doesn't need sponsorship
        ({"work_mode": "onsite", "board_location": "Austin, TX"}, None),  # location check off
    ],
)
def test_dealbreakers(changes, dealbreaker):
    r = score_brief(brief([item("SQL")], **changes), PROFILE, RULES, VOCAB, TODAY)
    assert r.dealbreakers == ([dealbreaker] if dealbreaker else [])
    assert r.decision == ("skip" if dealbreaker else "apply_referral")


def test_sponsorship_dealbreaker_when_the_profile_needs_it():
    applicant = copy.deepcopy(PROFILE.applicant)
    applicant["work_authorization"]["needs_sponsorship_now"] = True
    needs = replace(PROFILE, applicant=applicant)
    r = score_brief(brief([item("SQL")], sponsorship="not_available"), needs, RULES, VOCAB, TODAY)
    assert r.dealbreakers == ["sponsorship: the posting won't sponsor and the profile needs it"]


def test_only_the_off_location_check_exists_yet(tmp_path):
    path = tmp_path / "rules.toml"
    text = (REPO_ROOT / "config" / "fit_scoring.toml").read_text(encoding="utf-8")
    path.write_text(text.replace('location_check = "off"', 'location_check = "states"'),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="location_check"):
        load_rules(path)


# ---------------------------------------------------------------- stored scores


def _store_brief(db, posting_version_id, b, model="m"):
    db.execute(
        "insert into agents.llm_calls (request_hash, prompt_name, prompt_version, model,"
        " served_model, effort, input_hash, output, stop_reason, input_tokens, output_tokens)"
        " values (%s, 'jd-analysis', 'jd-analysis@3', %s, %s, 'medium', 'h', '{}', 'end_turn',"
        " 1, 1) returning llm_call_id", (f"r{posting_version_id}{model}", model, model),
    )
    call_id = db.execute("select max(llm_call_id) from agents.llm_calls").fetchone()[0]
    db.execute(
        "insert into agents.jd_briefs (posting_version_id, prompt_version, model, scope_version,"
        " llm_call_id, brief) values (%s, 'jd-analysis@3', %s, 2, %s, %s)",
        (posting_version_id, model, call_id, json.dumps(b)),
    )


@pytest.fixture
def briefed(db, greenhouse_jobs):
    from datetime import UTC, datetime
    from uuid import uuid4

    from pipeline.load import load_jobs

    run_id = uuid4()
    db.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')", (run_id,),
    )
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, run_id, datetime.now(UTC))
    ids = [r[0] for r in db.execute(
        "select posting_version_id from raw.job_postings order by 1").fetchall()]
    _store_brief(db, ids[0], brief([item("SQL"), item("Python")]))
    _store_brief(db, ids[1], brief([item("Kafka"), item("Scala")]))
    return db, ids


@pytest.mark.db
def test_run_stores_scores_once_per_profile_and_rules(briefed, tmp_path):
    db, ids = briefed
    kwargs = {"rules": RULES, "vocab": VOCAB, "today": TODAY,
              "brief_prompt_version": "jd-analysis@3", "brief_model": "m"}
    first = run(db, profile=PROFILE, **kwargs)
    assert first.scored == 2
    rows = db.execute(
        "select posting_version_id, decision, score, rules_version, vocabulary_version,"
        " profile_fingerprint from agents.fit_scores order by 1").fetchall()
    assert [(r[0], r[1]) for r in rows] == [(ids[0], "apply_referral"), (ids[1], "skip")]
    assert rows[0][5] == profile_fingerprint(SAMPLE)

    run(db, profile=PROFILE, **kwargs)  # same inputs: nothing new
    assert db.execute("select count(*) from agents.fit_scores").fetchone()[0] == 2

    edited = tmp_path / "profile"
    shutil.copytree(SAMPLE, edited)
    bank = edited / "evidence_bank.toml"
    bank.write_text(bank.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    run(db, profile=load_profile(edited), only=[ids[0]], **kwargs)  # new fingerprint: new row
    assert db.execute("select count(*) from agents.fit_scores").fetchone()[0] == 3


@pytest.mark.db
def test_the_more_capable_models_brief_is_scored_and_recorded(briefed):
    """Decision #48: briefs from several models; the strongest one's brief counts."""
    from agents.fit_scoring import load_briefs

    db, ids = briefed  # both postings already have a brief from model "m"
    _store_brief(db, ids[0], brief([item("Kafka")]), model="claude-haiku-5-5")
    _store_brief(db, ids[0], brief([item("SQL"), item("Python")]), model="claude-opus-5-5")
    rows = {pv: b for pv, b, _ in load_briefs(db, "jd-analysis@3")}
    assert [i["skill"] for i in rows[ids[0]]["must_haves"]] == ["SQL", "Python"]  # Opus's
    assert len(rows) == 2  # one brief per posting

    run(db, profile=PROFILE, rules=RULES, vocab=VOCAB, today=TODAY,
        brief_prompt_version="jd-analysis@3")
    models = dict(db.execute("select posting_version_id, brief_model from agents.fit_scores"))
    assert models == {ids[0]: "claude-opus-5-5", ids[1]: "m"}


@pytest.mark.db
def test_run_reads_the_posting_text_for_the_clearance_rule(briefed):
    from pipeline.gate_step import gate_pending

    db, ids = briefed
    gate_pending(db)
    db.execute(
        "update gate.results set cleaned_text = 'Must hold an active Secret clearance.'"
        " where posting_version_id = %s", (ids[0],),
    )
    result = run(
        db, profile=PROFILE, rules=RULES, vocab=VOCAB, today=TODAY,
        brief_prompt_version="jd-analysis@3", brief_model="m",
    )
    decisions = {posting_version_id: r for posting_version_id, _, r in result.results}
    assert decisions[ids[0]]["dealbreakers"][0].startswith("clearance:")
    assert not any(d.startswith("clearance:") for d in decisions[ids[1]]["dealbreakers"])
