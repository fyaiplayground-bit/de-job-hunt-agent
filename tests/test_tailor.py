"""Tests for the tailoring loop and its fact checks against the fictional sample (decision #38).
FakeClient stands in for the API; nothing is paid for. The point of most of these: a made-up claim
can't reach the page, whatever an LLM writes."""

import copy
import json
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from agents.fit_scoring import load_rules, load_vocabulary, score_brief
from agents.llm import FakeClient
from agents.pdf_checks import check_pdf
from agents.profile import check_resume, load_profile
from agents.resume_checks import (
    check_bullets,
    check_facts,
    check_no_invented_skills,
    check_no_unknown_names,
    check_quality,
    keyword_coverage,
    mentions,
)
from agents.resume_doc import parse_resume
from agents.skills import load_skill
from agents.tailor import (
    DRAFT_SCHEMA,
    REVIEW_SCHEMA,
    EditError,
    Job,
    apply_edit,
    build_resume,
    choose_jobs,
    clean_draft,
    drafter_input,
    pdf_name,
    reviewer_input,
    store,
    tailor_job,
    trim_one_bullet,
)
from agents.tailor_review import (
    changes_md,
    not_covered_md,
    review_page,
    write_index,
    write_job_files,
)
from pipeline.config import REPO_ROOT, LlmSettings

SAMPLE = REPO_ROOT / "data" / "sample"
PROFILE = load_profile(SAMPLE)
BANK = PROFILE.bank
VOCAB = load_vocabulary()
RULES = load_rules()
TODAY = date(2026, 11, 3)
SETTINGS = LlmSettings(model="claude-opus-5-5", effort="medium")
DRAFTER = load_skill("resume-tailoring")
REVIEWER = load_skill("resume-reviewer")
POSTING_TEXT = "We need a data engineer. SECRET-WORD-ONLY-IN-THE-POSTING. Python, SQL and Kafka."

BRIEF = {
    "company": "Acme Data",
    "title": "Data Engineer",
    "url": "https://example.com/job",
    "archetype": "pipeline_de",
    "seniority": "mid",
    "work_mode": "remote",
    "must_haves": [
        {"skill": "SQL", "weight": "core", "exact_phrases": ["SQL"]},
        {"skill": "Python", "weight": "core", "exact_phrases": ["Python"]},
        {"skill": "Data pipelines", "weight": "normal", "exact_phrases": ["data pipelines"]},
        {"skill": "Apache Kafka", "weight": "normal", "exact_phrases": ["Kafka"]},
    ],
    "nice_to_haves": [{"skill": "Snowflake", "exact_phrases": ["Snowflake"]}],
    "hidden_signals": [],
    "safety_flags": [],
}
DRAFT = {
    "headline": "Data Engineer · SQL / Python / AWS",
    "summary": "Business Intelligence Engineer who builds data pipelines in SQL and Python.",
    "experience": [
        {
            "where": "quillfeather-bie",
            "bullets": [
                {
                    "text": "Built daily data pipelines in Python loading 6 source systems into "
                    "Redshift, cutting the refresh from about 5 hours to 40 minutes",
                    "evidence": ["qf-glue-redshift"],
                },
                {
                    "text": "Designed a star schema in SQL with 4 fact and 12 dimension tables",
                    "evidence": ["qf-star-schema"],
                },
            ],
        },
        {
            "where": "brightmoor-analyst",
            "bullets": [
                {
                    "text": "Wrote nightly ETL jobs in Python covering 14 warehouses",
                    "evidence": ["bm-nightly-etl"],
                },
            ],
        },
    ],
    "projects": [
        {
            "where": "bikeshare-pipeline",
            "bullets": [
                {
                    "text": "Built 9 dbt models with 21 tests on PostgreSQL in Docker",
                    "evidence": ["bs-dbt-models"],
                },
            ],
        },
    ],
    "skills": ["SQL", "Python", "Data pipelines", "Amazon Redshift", "dbt"],
    "changes": [{"edit": "Led with pipelines", "serves": "Data pipelines"}],
}
PASS_REVIEW = {
    "verdict": "pass",
    "seven_second_answer": "A data engineer",
    "edits": [],
    "notes": [],
}


def make_job(posting_version_id=1, **changes):
    brief = {**BRIEF, **changes}
    fit = score_brief(brief, PROFILE, RULES, VOCAB, TODAY, POSTING_TEXT).as_json()
    return Job(posting_version_id, brief, POSTING_TEXT, fit)


JOB = make_job()


def draft(**changes):
    return {**copy.deepcopy(DRAFT), **changes}


def edit(kind, old="", new="", where="", evidence=(), reason="because"):
    return {
        "kind": kind,
        "old": old,
        "new": new,
        "where": where,
        "evidence": list(evidence),
        "reason": reason,
    }


def client_with(reviews, draft_output=None):
    """Answers the drafter with a draft, and each review call with the next review given."""
    queue = list(reviews)

    def answer(request):
        if request.prompt_name == "resume-tailoring":
            return draft_output or DRAFT
        return queue.pop(0) if queue else PASS_REVIEW

    return FakeClient(answer=answer)


@pytest.fixture
def no_db():
    """`ask` needs a connection; this one remembers nothing, so every call reaches the client."""

    class Nothing:
        def execute(self, sql, params=None):
            class Row:
                def fetchone(self):
                    return (1,) if "insert" in sql else None

            return Row()

    return Nothing()


# ---------------------------------------------------------------- code owns the facts


def test_build_resume_prints_facts_from_the_bank():
    resume = build_resume(draft(), PROFILE)
    assert check_resume(resume, BANK, PROFILE.applicant, lambda _: True) == []
    assert "**Business Intelligence Engineer** · Quillfeather Outdoor · Denver, CO" in resume
    assert "Mar 2021 - Present" in resume
    assert "**B.A. Economics** · Front Range State University · May 2017" in resume
    assert "Denver, CO · alex.sample@example.com · (303) 555-0142 · example.com/" in resume
    assert "**Bike-Share Trips Pipeline** (in progress) · example.com/alex-sample/" in resume
    assert "Spark practice" not in resume  # a project without bullets stays off
    assert "example.com/alex-sample/code" in resume.splitlines()[3]  # GitHub in the header


def test_a_role_without_a_city_has_no_trailing_separator():
    from dataclasses import replace

    roles = (replace(BANK.roles[0], location=""), *BANK.roles[1:])
    profile = replace(PROFILE, bank=replace(BANK, roles=roles))
    resume = build_resume(draft(), profile)
    assert "**Business Intelligence Engineer** · Quillfeather Outdoor\n" in resume


def test_built_resume_parses_and_keeps_every_line():
    doc = parse_resume(build_resume(draft(), PROFILE))
    assert doc.headline == DRAFT["headline"]
    assert [section.heading for section in doc.sections] == [
        "Summary",
        "Experience",
        "Projects",
        "Skills",
        "Education",
    ]
    assert len(doc.sections[1].entries[0].bullets) == 2


def test_an_llm_cannot_add_a_role_by_naming_one():
    fake = draft(
        experience=[
            {
                "where": "google-staff",
                "bullets": [
                    {"text": "Ran all of Google", "evidence": ["qf-git"]},
                ],
            }
        ]
    )
    resume = build_resume(fake, PROFILE)
    assert "Google" not in resume
    assert any("'google-staff' is not in the Evidence Bank" in p for p in check_bullets(fake, BANK))


def test_clean_draft_flattens_line_breaks():
    messy = draft(summary="one\n\ntwo  three")
    messy["experience"][0]["bullets"][0]["text"] = "Built\nthings"
    tidy = clean_draft(messy)
    assert tidy["summary"] == "one two three"
    assert tidy["experience"][0]["bullets"][0]["text"] == "Built things"


# ---------------------------------------------------------------- fact checks


def test_the_good_draft_passes_every_fact_check():
    assert (
        check_facts(draft(), build_resume(draft(), PROFILE), PROFILE, BRIEF, JOB.fit, VOCAB) == []
    )


@pytest.mark.parametrize(
    "text, evidence, expected",
    [
        ("Built things", [], "cites no evidence"),
        ("Built things", ["no-such-entry"], "unknown evidence 'no-such-entry'"),
        ("Built things", ["bm-nightly-etl"], "belongs to 'brightmoor-analyst'"),
        ("Loaded 60 source systems", ["qf-glue-redshift"], "the number 60"),
        # 14 is a real number in the bank, but not in the evidence this bullet cites.
        ("Loaded 14 source systems", ["qf-glue-redshift"], "the number 14"),
    ],
)
def test_a_bullet_must_trace_to_its_own_evidence(text, evidence, expected):
    bad = draft()
    bad["experience"][0]["bullets"][0] = {"text": text, "evidence": evidence}
    assert any(expected in problem for problem in check_bullets(bad, BANK))


def test_numbers_glued_to_letters_are_not_claims():
    fine = draft()
    fine["experience"][0]["bullets"][0] = {
        "text": "Landed files in S3 before loading Redshift",
        "evidence": ["qf-glue-redshift"],
    }
    assert check_bullets(fine, BANK) == []


@pytest.mark.parametrize(
    "text", ["Modeled SCD Type 2 dimensions", "Modeled SCD Type 1 and Type 2 dimensions",
             "Modeled SCD Type 1/2 dimensions"],
)
def test_scd_types_are_labels_not_quantities(text):
    """Decision #50: "Type 2" names a kind of dimension; no metric has to back it."""
    fine = draft()
    fine["experience"][0]["bullets"][1] = {"text": text, "evidence": ["qf-star-schema"]}
    assert check_bullets(fine, BANK) == []


@pytest.mark.parametrize(
    "text, flagged",
    [
        ("Added data quality checks to every pipeline", "every pipeline"),
        ("Tuned all of the tables in Redshift", "all of the tables"),
        ("Added checks to every production pipeline", "every production pipeline"),
        ("Added data quality checks for each pipeline", "for each pipeline"),  # reviewer's dodge
        ("Built a driver that checks each change before merge", None),  # not a scope claim
        ("Built tooling that tests each pipeline change against real data", None),
        ("Built tooling that tests every pipeline change before merge", None),
        ("Added data quality checks to the Glue loads", None),
        ("Gave all engineers a faster review", None),  # not a scope claim about data
    ],
)
def test_absolute_claims_must_come_from_the_evidence(text, flagged):
    """Decision #50: "every pipeline" needs evidence that says so."""
    d = draft()
    d["experience"][0]["bullets"][0] = {"text": text, "evidence": ["qf-data-quality"]}
    problems = [p for p in check_bullets(d, BANK) if "absolute claim" in p]
    assert problems == ([] if flagged is None else [problems[0]])
    if flagged:
        assert repr(flagged) in problems[0]


@pytest.mark.parametrize(
    "where, text",
    [
        ("summary", "Engineer with deep Kafka experience."),  # the job asks; the bank has none
        ("summary", "Engineer who knows Snowflake."),  # a nice-to-have the bank lacks
        ("summary", "Familiar with Kubernetes."),  # the job didn't ask, the vocabulary knows it
        ("skills", ["SQL", "Apache Kafka"]),
    ],
)
def test_a_skill_with_no_evidence_cannot_appear(where, text):
    bad = draft(**{where: text})
    assert check_no_invented_skills(bad, BRIEF, JOB.fit, BANK, VOCAB)


def test_a_bullet_cannot_slip_in_a_tool_either():
    bad = draft()
    bad["experience"][0]["bullets"][0]["text"] = "Built Kafka streams with Python"
    assert any("Kafka" in p for p in check_no_invented_skills(bad, BRIEF, JOB.fit, BANK, VOCAB))


@pytest.mark.parametrize(
    "text, word",
    [
        ("Deployed the pipelines with Terraform", "Terraform"),  # nobody asked; not in the bank
        ("Built streaming jobs in Rust and SQL", "Rust"),
        ("Led the Platform Guild", "Guild"),
    ],
)
def test_a_name_nobody_listed_is_caught(text, word):
    bad = draft()
    bad["experience"][0]["bullets"][0]["text"] = text
    problems = check_no_unknown_names(bad, BRIEF, JOB.fit, BANK, VOCAB)
    assert any(repr(word) in problem for problem in problems)


def test_names_from_the_bank_and_the_jobs_wording_are_fine():
    fine = draft()
    fine["experience"][0]["bullets"][0]["text"] = (
        "Built Data Pipelines with AWS Glue and Slack alerts into Amazon Redshift"
    )
    assert check_no_unknown_names(fine, BRIEF, JOB.fit, BANK, VOCAB) == []


def test_skills_may_use_the_jobs_wording_for_a_real_skill():
    fine = draft(skills=["SQL", "Data pipelines", "ETL/ELT pipelines", "AWS"])
    assert check_facts(fine, build_resume(fine, PROFILE), PROFILE, BRIEF, JOB.fit, VOCAB) == []


def test_skills_may_not_list_what_the_profile_lacks():
    bad = draft(skills=["SQL", "Fortran"])
    problems = check_facts(bad, build_resume(bad, PROFILE), PROFILE, BRIEF, JOB.fit, VOCAB)
    assert any("Fortran" in problem for problem in problems)


def test_a_made_up_number_in_the_headline_is_caught():
    bad = draft(headline="Data Engineer with 15 years")
    problems = check_facts(bad, build_resume(bad, PROFILE), PROFILE, BRIEF, JOB.fit, VOCAB)
    assert "the number 15 in the headline is in no Evidence Bank metric" in problems


def test_mentions_is_whole_word_and_short_terms_match_case():
    assert mentions("Built with Spark daily", "spark")
    assert not mentions("Sparkling", "Spark")
    assert mentions("Written in Go", "Go")
    assert not mentions("a go-live date", "Go")


# ---------------------------------------------------------------- quality checks


def test_the_good_draft_passes_every_quality_check():
    assert check_quality(draft(), BRIEF, JOB.fit) == []


def test_keyword_coverage_counts_the_covered_must_haves():
    assert keyword_coverage(draft(), BRIEF, JOB.fit) == (1.0, [])
    thin = draft(summary="Builds things.", skills=["dbt"])
    thin["experience"] = []
    share, missing = keyword_coverage(thin, BRIEF, JOB.fit)
    assert share < 0.8
    assert "Data pipelines" in missing


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"headline": "Experienced Professional"}, "doesn't name a target role"),
        ({"projects": []}, "no project"),
    ],
)
def test_quality_problems(changes, expected):
    assert any(expected in p for p in check_quality(draft(**changes), BRIEF, JOB.fit))


def test_weak_or_long_or_numberless_bullets_are_sent_back():
    bad = draft()
    bad["experience"][0]["bullets"] = [
        {"text": "Responsible for the warehouse", "evidence": ["qf-git"]},
        {"text": "Built " + "very " * 60 + "much", "evidence": ["qf-git"]},
    ]
    bad["experience"][1]["bullets"] = []
    bad["projects"][0]["bullets"][0]["text"] = "Modeled trips in dbt"
    problems = check_quality(bad, BRIEF, JOB.fit)
    assert any("opens weakly" in p for p in problems)
    assert any("over 220 characters" in p for p in problems)
    assert any("bullets carry a number" in p for p in problems)


# ---------------------------------------------------------------- reviewer edits


def test_replace_changes_one_field_and_can_cite_more_evidence():
    new = apply_edit(
        draft(),
        edit(
            "replace",
            "Designed a star schema",
            "Modeled a star schema",
            evidence=["qf-query-tuning"],
        ),
        PROFILE,
    )
    bullet = new["experience"][0]["bullets"][1]
    assert bullet["text"].startswith("Modeled a star schema")
    assert bullet["evidence"] == ["qf-star-schema", "qf-query-tuning"]
    assert DRAFT["experience"][0]["bullets"][1]["text"].startswith("Designed")  # original untouched


@pytest.mark.parametrize(
    "bad_edit",
    [
        edit("replace", "no such words here", "x"),
        edit("replace", "Python", "Java"),  # in several fields: which one?
        edit("replace", "", "x"),
        edit("remove_bullet", "not a bullet"),
        edit("move_first", "not a bullet"),
        edit("add_bullet", new="x", where="no-such-role"),
        edit("add_skill", new="sql"),  # already there
        edit("rewrite_everything", new="x"),
    ],
)
def test_an_edit_that_does_not_fit_is_refused(bad_edit):
    with pytest.raises(EditError):
        apply_edit(draft(), bad_edit, PROFILE)


def test_other_edit_kinds():
    second = DRAFT["experience"][0]["bullets"][1]["text"]
    moved = apply_edit(draft(), edit("move_first", second), PROFILE)
    assert moved["experience"][0]["bullets"][0]["text"] == second
    removed = apply_edit(draft(), edit("remove_bullet", second), PROFILE)
    assert len(removed["experience"][0]["bullets"]) == 1
    added = apply_edit(draft(), edit("add_skill", new="Docker"), PROFILE)
    assert added["skills"][-1] == "Docker"
    new_project = apply_edit(
        draft(),
        edit(
            "add_bullet",
            new="Wrote PySpark joins",
            where="spark-course",
            evidence=["spark-exercises"],
        ),
        PROFILE,
    )
    assert new_project["projects"][-1]["where"] == "spark-course"


# ---------------------------------------------------------------- the whole loop


def run_job(no_db, tmp_path, reviews=(), draft_output=None, job=JOB):
    client = client_with(reviews, draft_output)
    tailored = tailor_job(no_db, client, job, PROFILE, VOCAB, SETTINGS, DRAFTER, REVIEWER, tmp_path)
    return tailored, client


def names(client):
    return [request.prompt_name for request in client.requests]


def test_a_clean_draft_takes_one_review_and_is_ready(no_db, tmp_path):
    tailored, client = run_job(no_db, tmp_path)
    assert tailored.status == "ready"
    assert names(client) == ["resume-tailoring", "resume-reviewer"]
    assert tailored.pdf.is_file()
    assert tailored.report.pages == 1
    assert "Quillfeather Outdoor" in tailored.report.text


def test_a_good_edit_is_applied(no_db, tmp_path):
    review = {
        **PASS_REVIEW,
        "verdict": "revise",
        "edits": [
            edit("replace", "Designed a star schema", "Modeled a star schema"),
        ],
    }
    tailored, _ = run_job(no_db, tmp_path, [review])
    assert "Modeled a star schema" in tailored.resume
    assert tailored.history[0]["applied"]
    assert tailored.status == "ready"


@pytest.mark.parametrize(
    "bad_edit",
    [
        edit("replace", "Designed a star schema", "Designed a Kafka stream"),  # no evidence
        edit("replace", "4 fact tables", "40 fact tables"),  # a number it doesn't have
        edit("add_skill", new="Snowflake"),
        edit("add_bullet", new="Ran it all", where="quillfeather-bie", evidence=["no-such-entry"]),
    ],
)
def test_an_edit_that_breaks_a_fact_is_refused_and_never_reaches_the_page(
    no_db, tmp_path, bad_edit
):
    review = {**PASS_REVIEW, "verdict": "revise", "edits": [bad_edit]}
    tailored, client = run_job(no_db, tmp_path, [review])
    rejected = tailored.history[0]["rejected"]
    assert rejected and rejected[0]["refused_because"]
    assert "Kafka" not in tailored.report.text
    assert "Snowflake" not in tailored.report.text
    assert "40 fact tables" not in tailored.report.text
    assert names(client).count("resume-reviewer") == 2  # told what was refused, one more round
    assert tailored.status == "ready"  # the draft itself stayed clean


def test_second_round_sees_what_was_refused(no_db, tmp_path):
    review = {**PASS_REVIEW, "verdict": "revise", "edits": [edit("add_skill", new="Snowflake")]}
    _, client = run_job(no_db, tmp_path, [review])
    second = json.loads(client.requests[2].user.removeprefix("<data>\n").removesuffix("\n</data>"))
    assert second["rejected_edits"][0]["new"] == "Snowflake"


def test_a_draft_with_an_invented_fact_is_not_ready_if_the_reviewer_misses_it(no_db, tmp_path):
    bad = draft(summary="Engineer with deep Kafka experience.")
    tailored, client = run_job(no_db, tmp_path, draft_output=bad)
    assert tailored.status == "needs_review"
    assert any("Kafka" in problem for problem in tailored.all_problems)
    assert names(client).count("resume-reviewer") == 2  # stops at the limit


def test_the_reviewer_can_fix_a_fact_problem(no_db, tmp_path):
    bad = draft(summary="Engineer with deep Kafka experience in SQL and Python data pipelines.")
    review = {
        **PASS_REVIEW,
        "verdict": "revise",
        "edits": [
            edit("replace", "deep Kafka experience", "deep pipeline experience"),
        ],
    }
    tailored, _ = run_job(no_db, tmp_path, [review], draft_output=bad)
    assert tailored.status == "ready"
    assert "Kafka" not in tailored.report.text


def test_overflow_is_trimmed_to_one_page_and_recorded(no_db, tmp_path):
    long = draft()
    long["experience"][0]["bullets"] = [
        {
            "text": f"Designed a star schema in SQL with 4 fact tables, version {chr(97 + i)} " * 2,
            "evidence": ["qf-star-schema"],
        }
        for i in range(26)
    ]
    long = clean_draft(long)
    tailored, _ = run_job(no_db, tmp_path, draft_output=long)
    assert tailored.report.pages == 1
    assert tailored.history[-1]["trimmed_to_fit_one_page"]
    assert len(tailored.draft["experience"][0]["bullets"]) < 26


def test_trim_cuts_the_end_of_the_longest_list_and_keeps_one_each():
    d = draft()
    assert trim_one_bullet(d).startswith("Designed a star schema")
    assert trim_one_bullet(d) is None  # every entry is down to one bullet


def test_trim_keeps_a_bullet_that_alone_says_a_keyword():
    """Decision #50: the last bullet (e.g. one the reviewer added) stays when only it says a
    covered must-have; the bullet that says nothing new goes instead."""
    d = draft()
    d["experience"][0]["bullets"] = [
        {"text": "Set up Athena tables over 2 years of clickstream logs in S3",
         "evidence": ["qf-athena-clickstream"]},
        *d["experience"][0]["bullets"],
    ]
    d["experience"][0]["bullets"][-1]["text"] = "Designed a star schema in SQL"  # only SQL here
    d["experience"][0]["bullets"][1]["text"] = "Built daily data pipelines in Python"
    # Python and ETL are also said by the other role, so neither of the first two bullets loses a
    # keyword; the tie falls back to the later one. The old rule would have cut the SQL bullet.
    assert trim_one_bullet(d, JOB.brief, JOB.fit) == "Built daily data pipelines in Python"
    assert trim_one_bullet(d, JOB.brief, JOB.fit).startswith("Set up Athena tables")
    assert [b["text"] for b in d["experience"][0]["bullets"]] == ["Designed a star schema in SQL"]


def test_on_a_tie_trim_keeps_the_bullet_the_reviewer_added():
    """Decision #50: a bullet the reviewer added for the posting goes after the drafter's own."""
    d = apply_edit(
        draft(),
        edit("add_bullet", new="Moved the BI team's SQL into Git with code review",
             where="quillfeather-bie", evidence=["qf-git"]),
        PROFILE,
    )
    assert d["experience"][0]["bullets"][-1]["added_by_review"] is True
    removed = trim_one_bullet(d, JOB.brief, JOB.fit)
    assert removed != "Moved the BI team's SQL into Git with code review"


# ---------------------------------------------------------------- what each LLM sees


def test_the_drafter_never_reads_the_posting():
    data = drafter_input(JOB, PROFILE)
    assert "SECRET-WORD-ONLY-IN-THE-POSTING" not in data
    assert '"must_haves"' in data


def test_the_reviewer_reads_the_posting_and_code_problems():
    data = reviewer_input(JOB, PROFILE, draft(), ["a problem"], [])
    assert "SECRET-WORD-ONLY-IN-THE-POSTING" in data
    assert "a problem" in data


def test_interview_stories_stay_out_of_both():
    story = BANK.evidence[0].story
    assert story not in drafter_input(JOB, PROFILE)
    assert story not in reviewer_input(JOB, PROFILE, draft(), [], [])


def test_schemas_require_every_field():
    for schema in (DRAFT_SCHEMA, REVIEW_SCHEMA):
        assert set(schema["required"]) == set(schema["properties"])
        assert schema["additionalProperties"] is False


# ---------------------------------------------------------------- choosing jobs


def test_choose_jobs_never_tailors_a_skip():
    good, skip = make_job(1), make_job(2, salary={"min": 1000, "max": 50000, "currency": "USD"})
    assert skip.fit["decision"] == "skip"
    assert choose_jobs([good, skip], [], 5) == ([good], [])
    chosen, refused = choose_jobs([good, skip], [1, 2, 3], None)
    assert chosen == [good]
    assert refused[0].startswith("#2: scored skip")
    assert refused[1] == "#3: no current brief"


def test_pdf_name():
    assert pdf_name(PROFILE, JOB) == "AlexSample_DataEngineer_AcmeData.pdf"
    analytics = make_job(archetype="analytics_engineer")
    assert pdf_name(PROFILE, analytics) == "AlexSample_AnalyticsEngineer_AcmeData.pdf"


# ---------------------------------------------------------------- what a person reads


def test_review_files(no_db, tmp_path):
    review = {
        **PASS_REVIEW,
        "verdict": "revise",
        "edits": [
            edit("replace", "Designed a star schema", "Modeled a star schema"),
            edit("add_skill", new="Snowflake", reason="asked for"),
        ],
    }
    tailored, _ = run_job(no_db, tmp_path, [review])
    page = write_job_files(tailored, tmp_path)
    text = page.read_text(encoding="utf-8")
    assert "SECRET-WORD-ONLY-IN-THE-POSTING" in text  # the posting, side by side
    assert "data:image/png;base64," in text
    assert "Apache Kafka" in text  # not covered is listed
    assert (page.parent / tailored.pdf.name).is_file()
    assert "Modeled a star schema" in changes_md(tailored)
    assert "REFUSED" in changes_md(tailored)
    assert "Apache Kafka" in not_covered_md(tailored)
    assert (page.parent / "resume.md").is_file()
    index = write_index([tailored], tmp_path).read_text(encoding="utf-8")
    assert f"{tailored.pdf.parent.name}/review.html" in index


def test_review_page_escapes_the_posting(no_db, tmp_path):
    hostile = make_job(title="Data Engineer <b>now</b>")
    hostile = Job(1, hostile.brief, "<script>alert(1)</script>", hostile.fit)
    tailored, _ = run_job(no_db, tmp_path, job=hostile)
    page = review_page(tailored)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert "<b>now</b>" not in page


def test_pdf_passes_its_own_checks_when_read_back(no_db, tmp_path):
    tailored, _ = run_job(no_db, tmp_path)
    report = check_pdf(tailored.pdf, expected_lines=parse_resume(tailored.resume).lines())
    assert report.failures == ()


# ---------------------------------------------------------------- stored, and free the second time


@pytest.mark.db
def test_store_and_a_rerun_costs_nothing(db, greenhouse_jobs, tmp_path):
    from pipeline.load import load_jobs

    run_id = uuid4()
    db.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')",
        (run_id,),
    )
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, run_id, datetime.now(UTC))
    posting_version_id = db.execute(
        "select min(posting_version_id) from raw.job_postings"
    ).fetchone()[0]
    job = make_job(posting_version_id)

    client = client_with([])
    first = tailor_job(db, client, job, PROFILE, VOCAB, SETTINGS, DRAFTER, REVIEWER, tmp_path)
    assert len(client.requests) == 2
    assert first.paid_now_usd > 0
    store(db, first, "fingerprint", SETTINGS, DRAFTER, REVIEWER)

    again = client_with([])
    second = tailor_job(db, again, job, PROFILE, VOCAB, SETTINGS, DRAFTER, REVIEWER, tmp_path)
    assert again.requests == []  # both answers came from agents.llm_calls
    assert second.paid_now_usd == 0
    assert second.draft == first.draft
    store(db, second, "fingerprint", SETTINGS, DRAFTER, REVIEWER)  # same key: updated, not doubled
    status, rounds, count = db.execute(
        "select max(status), max(review_rounds), count(*) from agents.tailored_resumes"
    ).fetchone()
    assert (status, rounds, count) == ("ready", 1, 1)


# ---------------------------------------------------------------- found by the first live run


def test_a_word_opening_a_new_sentence_is_not_a_product_name():
    fine = draft(summary="Business Intelligence Engineer. Builds pipelines; Leads reviews.")
    assert check_no_unknown_names(fine, BRIEF, JOB.fit, BANK, VOCAB) == []


def test_first_person_is_sent_back():
    bad = draft(summary="I build data pipelines in SQL and Python.")
    assert any("first person" in problem for problem in check_quality(bad, BRIEF, JOB.fit))


# ---------------------------------------------------------------- FL's notes on the trial, 11/04


@pytest.mark.parametrize(
    "where, text",
    [
        ("summary", "Business Intelligence Engineer moving into analytics engineering."),
        ("summary", "Transitioning to data engineering after years in BI."),
        ("headline", "Aspiring Data Engineer"),
        ("summary", "Engineer making a career change."),
    ],
)
def test_transition_wording_is_sent_back(where, text):
    problems = check_quality(draft(**{where: text}), BRIEF, JOB.fit)
    assert any("transition wording" in problem for problem in problems)


def test_describing_a_system_moving_is_fine():
    fine = draft()
    fine["experience"][0]["bullets"][0]["text"] = "Moved the team's SQL into Git with 6 reviews"
    assert not any("transition" in p for p in check_quality(fine, BRIEF, JOB.fit))


EITHER_OR = {
    **BRIEF,
    "must_haves": [
        {
            "skill": "Python or Java or Terraform",
            "weight": "core",
            "exact_phrases": ["Python", "Java", "Terraform"],
        },
        {"skill": "SQL", "weight": "core", "exact_phrases": ["SQL"]},
    ],
    "nice_to_haves": [],
}


def test_an_either_or_entry_is_covered_by_one_part_but_gives_no_right_to_the_others():
    fit = score_brief(EITHER_OR, PROFILE, RULES, VOCAB, TODAY, "").as_json()
    assert fit["not_covered"] == []  # Python covers the entry
    bad = draft(summary="Engineer who writes Java and Python.")
    assert any("Java" in p for p in check_no_invented_skills(bad, EITHER_OR, fit, BANK, VOCAB))
    fine = draft(summary="Engineer who writes Python.")
    assert check_no_invented_skills(fine, EITHER_OR, fit, BANK, VOCAB) == []


def test_an_either_or_entry_lends_no_words_to_the_name_check():
    fit = score_brief(EITHER_OR, PROFILE, RULES, VOCAB, TODAY, "").as_json()
    bad = draft()
    bad["experience"][0]["bullets"][0]["text"] = "Deployed it with Terraform"
    problems = check_no_unknown_names(bad, EITHER_OR, fit, BANK, VOCAB)
    assert any("Terraform" in problem for problem in problems)


def test_review_page_uses_plain_labels(no_db, tmp_path):
    review = {
        **PASS_REVIEW,
        "verdict": "revise",
        "edits": [
            edit("replace", "Designed a star schema", "Modeled a star schema"),
        ],
    }
    tailored, _ = run_job(no_db, tmp_path, [review])
    page = review_page(tailored)
    assert "改写：原来" in page
    assert "[replace]" not in page
    assert "要修改" in page
    assert "不会上简历" in page


def test_a_phrase_made_of_words_the_bank_uses_is_not_invented():
    """The sample really has dbt tests, so a missing skill's phrase "dbt tests" stays allowed."""
    job = {
        **BRIEF,
        "nice_to_haves": [
            {
                "skill": "Data testing frameworks",
                "exact_phrases": ["dbt tests", "Great Expectations"],
            },
        ],
    }
    fit = score_brief(job, PROFILE, RULES, VOCAB, TODAY, "").as_json()
    fine = draft(summary="Engineer with dbt tests on every model.")
    assert check_no_invented_skills(fine, job, fit, BANK, VOCAB) == []
    bad = draft(summary="Engineer who runs Great Expectations.")
    assert any(
        "Great Expectations" in p for p in check_no_invented_skills(bad, job, fit, BANK, VOCAB)
    )
