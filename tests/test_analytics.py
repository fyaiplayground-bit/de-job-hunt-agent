"""The analytics layer (decision #41): dbt built and tested in the throwaway test database, the
coverage report on top of it, and the dashboard. dbt runs for real, so these take a few seconds."""

import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import yaml

from agents.coverage_report import coverage_lines, read_coverage
from agents.fit_scoring import run as score_all
from agents.profile import load_profile
from agents.skills import load_skill
from pipeline.analytics import (
    DBT_DIR,
    SYNONYMS_SEED,
    run_dbt,
    sync_profile_skills,
    write_synonyms_seed,
)
from pipeline.config import REPO_ROOT, LlmSettings
from pipeline.daily import DE_TITLE, DailySummary, render_report

SAMPLE = REPO_ROOT / "data" / "sample"
PROFILE = load_profile(SAMPLE)
SETTINGS = LlmSettings(model="claude-opus-5-5", effort="medium")


def test_dbt_and_the_daily_report_use_the_same_de_title_pattern():
    project = yaml.safe_load((DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8"))
    assert project["vars"]["de_title_pattern"] == DE_TITLE.pattern


def test_the_apply_bar_matches_the_scoring_rules():
    from agents.fit_scoring import load_rules

    project = yaml.safe_load((DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8"))
    assert project["vars"]["coverage_bar"] == load_rules().apply_bar


def test_the_committed_seed_matches_the_vocabulary(tmp_path):
    generated = tmp_path / "seed.csv"
    write_synonyms_seed(generated)
    assert generated.read_text(encoding="utf-8") == SYNONYMS_SEED.read_text(encoding="utf-8")


def test_the_repo_holds_no_profile_in_dbt():
    """The real profile reaches dbt through a database table, never a committed seed."""
    assert [path.name for path in (DBT_DIR / "seeds").iterdir()] == ["skill_synonyms.csv"]


def _coverage(**changes):
    period = {"jobs_scored": 40, "jobs_clearing_bar": 20, "coverage_share": 0.5}
    return {
        "periods": {
            "today": period,
            "last_30_days": {
                **period,
                "jobs_scored": 80,
                "jobs_clearing_bar": 44,
                "coverage_share": 0.55,
            },
            "last_7_days": period,
            "prior_7_days": {**period, "coverage_share": 0.4},
            **changes,
        },
        "archetypes": [{"archetype": "pipeline_de", "jobs_scored": 40, "coverage_share": 0.6}],
        "top_skills": [
            {
                "skill_name": "SQL",
                "status": "have",
                "must_have_jobs": 60,
                "must_have_share": 0.75,
                "jobs_30d": 80,
                "trend": "up",
            },
            {
                "skill_name": "Kafka",
                "status": "not_covered",
                "must_have_jobs": 8,
                "must_have_share": 0.1,
                "jobs_30d": 80,
                "trend": "not_enough_data",
            },
        ],
    }


def test_coverage_lines_carry_the_numbers_behind_each_figure():
    text = "\n".join(coverage_lines(_coverage()))
    assert "50%（40 个里 20 个）" in text
    assert "55%（80 个里 44 个）" in text
    assert "+10 个百分点" in text
    assert "数据管道 DE 60%（40 个）" in text
    assert "| SQL | 75%（60） | 已有 | ↑ |" in text
    assert "| Kafka | 10%（8） | 没覆盖 | 数据不够 |" in text


def test_a_small_week_gives_no_change_figure():
    small = {"jobs_scored": 5, "jobs_clearing_bar": 2, "coverage_share": 0.4}
    text = "\n".join(coverage_lines(_coverage(prior_7_days=small)))
    assert "数据不够（上周 5 个" in text
    assert "百分点" not in text


def test_no_data_says_so():
    empty = {"jobs_scored": 0, "jobs_clearing_bar": 0, "coverage_share": None}
    coverage = {
        "periods": {
            "today": empty,
            "last_30_days": empty,
            "last_7_days": empty,
            "prior_7_days": empty,
        },
        "archetypes": [],
        "top_skills": [],
    }
    assert any("还没有数据" in line for line in coverage_lines(coverage))


def test_coverage_never_recommends_what_to_study():
    text = "\n".join(coverage_lines(_coverage()))
    assert not re.search(r"建议|应该|去学|should|recommend", text, re.IGNORECASE)


def _summary(**changes):
    return DailySummary(local_date="2026-11-05", window_days=2, **changes)


def test_daily_report_has_the_coverage_section():
    text = render_report(_summary(analytics_status="ok", coverage=_coverage()))
    assert "## 技能覆盖" in text
    assert "| SQL |" in text


def test_daily_report_says_when_analytics_failed_and_goes_on():
    text = render_report(_summary(analytics_status="error", analytics_error="model broke"))
    assert "model broke" in text
    assert "## 各来源" not in text or "## 技能覆盖" in text


def test_daily_report_without_analytics_has_no_section():
    assert "技能覆盖" not in render_report(_summary())


@pytest.fixture
def built(db, greenhouse_jobs, monkeypatch):
    """Real postings, briefs and scores in the test database, with dbt built on them."""
    from psycopg.types.json import Jsonb

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
    ids = [
        r[0]
        for r in db.execute("select posting_version_id from raw.job_postings order by 1").fetchall()
    ]
    version = load_skill("jd-analysis").prompt_version
    must_haves = [
        ("Python or Java", "core"),
        ("SQL", "core"),
        ("Data pipelines", "normal"),
        ("Kafka", "normal"),
        ("AWS", "normal"),
    ]
    for posting_version_id in ids[:2]:
        call = db.execute(
            "insert into agents.llm_calls (request_hash, prompt_name, prompt_version, model,"
            " served_model, effort, input_hash, output, stop_reason, input_tokens, output_tokens,"
            " cost_usd) values (%s, 'jd-analysis', %s, %s, %s, 'medium', 'h', '{}', 'end_turn',"
            " 1, 1, 0.04) returning llm_call_id",
            (f"b{posting_version_id}", version, SETTINGS.model, SETTINGS.model),
        ).fetchone()[0]
        brief = {
            "company": "Acme",
            "title": "Data Engineer",
            "url": "https://jobs.lever.co/a/1",
            "archetype": "pipeline_de",
            "seniority": "mid",
            "work_mode": "remote",
            "years_required": 3,
            "sponsorship": "unstated",
            "must_haves": [
                {"skill": skill, "weight": weight, "exact_phrases": [skill]}
                for skill, weight in must_haves
            ],
            "nice_to_haves": [{"skill": "Tableau", "exact_phrases": ["Tableau"]}],
        }
        db.execute(
            "insert into agents.jd_briefs (posting_version_id, prompt_version, model,"
            " scope_version, llm_call_id, brief) values (%s, %s, %s, 2, %s, %s)",
            (posting_version_id, version, SETTINGS.model, call, Jsonb(brief)),
        )
    score_all(db, profile=PROFILE, brief_prompt_version=version, brief_model=SETTINGS.model)
    sync_profile_skills(db, SAMPLE)
    # dbt connects by itself, so it must be pointed at the test database too.
    monkeypatch.setenv("POSTGRES_DB", "jobhunt_test")
    result = run_dbt()
    assert result.ok, (result.failed, result.error)
    return db


@pytest.mark.db
def test_marts_are_built_and_right(built):
    db = built
    mentions = dict(
        db.execute(
            "select skill_part, status from analytics_skills.skill_mentions"
            " where posting_version_id = (select min(posting_version_id)"
            "  from agents.jd_briefs)"
        ).fetchall()
    )
    # Either/or is split, and Python covering the entry says nothing about Java.
    assert mentions["Python"] == "have"
    assert mentions["Java"] == "not_covered"
    assert mentions["Kafka"] == "not_covered"
    assert mentions["AWS"] == "have"  # a family: covered by Redshift and friends

    names = {
        row[0]: row[1]
        for row in db.execute(
            "select skill_name, must_have_jobs from analytics_marts.mart_skill_frequency"
        ).fetchall()
    }
    assert names["ETL"] == 2  # "Data pipelines" counted under one key
    assert "Data pipelines" not in names

    requirement = db.execute(
        "select is_covered from analytics_skills.skill_requirements"
        " where requirement = 'Python or Java' limit 1"
    ).fetchone()[0]
    assert requirement is True

    funnel = dict(db.execute("select stage, jobs_real from analytics_marts.mart_funnel").fetchall())
    assert funnel["Briefed by AI"] == 2
    assert funnel["Scored"] == 2
    assert funnel["Applied"] == 0


@pytest.mark.db
def test_coverage_report_reads_the_marts(built):
    coverage = read_coverage(built)
    today = coverage["periods"]["today"]
    assert today["jobs_scored"] == 2
    assert today["jobs_clearing_bar"] == 2
    assert coverage["top_skills"][0]["must_have_jobs"] == 2
    assert coverage["archetypes"][0]["archetype"] == "pipeline_de"
    assert any("100%（2 个里 2 个）" in line for line in coverage_lines(coverage))


@pytest.mark.db
def test_a_dbt_run_leaves_the_pipeline_tables_alone(built):
    before = built.execute("select count(*) from raw.job_postings").fetchone()[0]
    assert run_dbt().ok
    assert built.execute("select count(*) from raw.job_postings").fetchone()[0] == before


@pytest.mark.db
def test_dashboard_runs_without_errors(built):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert not app.error
    assert app.title[0].value == "Job Hunt Pipeline"
    assert [tab.label for tab in app.tabs] == ["Skills", "Coverage", "Funnel", "Pipeline"]
    labels = [metric.label for metric in app.metric]
    assert "Worth applying" in labels
