"""The approval queue (decision #40) against the fictional sample profile. FakeClient stands in for
the API; nothing is paid for. Most of these protect one of three promises: never the same job
twice, never a guessed answer, and never a fictional resume sent to a real company."""

import copy
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from agents.application_queue import (
    QueueError,
    answer_questions,
    batch_rows,
    build_batch,
    company_key,
    job_keys,
    load_queue_rules,
    pick_batch,
    set_status,
    site_kind,
    write_pack,
)
from agents.fit_scoring import load_rules, load_vocabulary, score_brief
from agents.llm import FakeClient
from agents.profile import load_profile
from agents.queue_review import pack_markdown, queue_page, write_page
from agents.tailor import Job
from pipeline.config import REPO_ROOT, LlmSettings

SAMPLE = REPO_ROOT / "data" / "sample"
PROFILE = load_profile(SAMPLE)
RULES = load_queue_rules()
SETTINGS = LlmSettings(model="claude-opus-5-5", effort="medium")
TODAY = date(2026, 11, 4)


def job(
    posting_id,
    score=60,
    company="Acme",
    title="Data Engineer",
    host="acme.example.com",
    decision="apply",
):
    brief = {"company": company, "title": title, "url": f"https://{host}/job/{posting_id}"}
    return Job(posting_id, brief, "text", {"score": score, "decision": decision})


def pick(jobs, rules=RULES, ids=(), job_keys_seen=(), title_keys_seen=()):
    return pick_batch(jobs, rules, set(ids), set(job_keys_seen), set(title_keys_seen))


def ids(batch):
    return [j.posting_version_id for j in batch.chosen]


# ---------------------------------------------------------------- picking


def test_best_score_first_up_to_the_batch_size():
    jobs = [job(i, score=50 + i, company=f"Company{i}", host=f"c{i}.example.com") for i in range(8)]
    assert ids(pick(jobs)) == [7, 6, 5, 4, 3]


def test_a_skip_is_never_picked():
    assert ids(pick([job(1, decision="skip")])) == []


@pytest.mark.parametrize(
    "first, second",
    [
        # The real pair from the 11/04 data: one hospital spelled two ways, same site.
        (
            dict(
                company="The University of Chicago Medicine",
                title="Analytics Engineer, Revenue Cycle",
                host="fa-etnf.oraclecloud.com",
            ),
            dict(
                company="UCM",
                title="Analytics Engineer, Revenue Cycle",
                host="fa-etnf.oraclecloud.com",
            ),
        ),
        # Same company under a longer name, posted on two boards.
        (
            dict(
                company="Cheil Worldwide", title="Senior Data Engineer, CRM", host="a.example.com"
            ),
            dict(company="Cheil", title="Senior Data Engineer, CRM", host="b.example.com"),
        ),
    ],
)
def test_the_same_job_under_two_names_is_picked_once(first, second):
    batch = pick([job(1, score=70, **first), job(2, score=60, **second)])
    assert ids(batch) == [1]
    assert batch.skipped[0][0].posting_version_id == 2
    assert "同一个" in batch.skipped[0][1]


def test_one_job_per_company_in_a_batch_and_the_other_is_reported():
    batch = pick(
        [
            job(1, score=70, title="Data Engineer", host="a.example.com"),
            job(2, score=60, title="Analytics Engineer", host="b.example.com"),
        ]
    )
    assert ids(batch) == [1]
    assert "这家公司" in batch.skipped[0][1]


def test_a_different_title_at_a_different_company_on_one_site_is_two_jobs():
    batch = pick(
        [
            job(1, company="Acme", title="Data Engineer", host="jobs.lever.co"),
            job(2, company="Beta", title="Analytics Engineer", host="jobs.lever.co"),
        ]
    )
    assert ids(batch) == [1, 2]


def test_earlier_batches_count():
    first = job(1)
    job_key, title_key = job_keys(first.brief)
    assert ids(pick([first], ids=[1])) == []
    other = job(2, company="Acme Inc.", host="other.example.com")  # same job, a new posting
    assert ids(pick([other], job_keys_seen=[job_key])) == []
    respelled = job(3, company="Different Name")  # same title and site
    assert ids(pick([respelled], title_keys_seen=[title_key])) == []


def test_jobs_past_the_batch_size_are_not_called_duplicates():
    jobs = [job(i, company=f"Co{i}", host=f"c{i}.example.com", title=f"T{i}") for i in range(8)]
    assert pick(jobs).skipped == []


@pytest.mark.parametrize(
    "name, key",
    [
        ("Cheil Worldwide", "cheil"),
        ("Publicis Groupe Holdings B.V", "publicis groupe b v"),
        ("Acme, Inc.", "acme"),
        ("The Group", "the group"),  # nothing left: keep every word
    ],
)
def test_company_key(name, key):
    assert company_key(name) == key


@pytest.mark.parametrize(
    "url, kind",
    [
        ("https://job-boards.greenhouse.io/x/jobs/1", "no_account"),
        ("https://jobs.lever.co/x/1", "no_account"),
        ("https://acme.wd1.myworkdayjobs.com/x", "account"),
        ("https://fa-x.fa.ocs.oraclecloud.com/y", "account"),
        ("https://www.adzuna.com/details/1", "aggregator"),
        ("https://careers.example.com/1", "unknown"),
        ("https://notlever.co/x", "unknown"),  # the end of the address, not any text in it
        ("", "unknown"),
    ],
)
def test_site_kind(url, kind):
    assert site_kind(url, RULES) == kind


# ---------------------------------------------------------------- answers: never guessed


def test_answers_come_from_the_profile():
    answered, for_fl = answer_questions(
        ["Are you authorized to work in the US?", "What are your salary expectations?"],
        PROFILE.applicant,
        RULES,
    )
    assert for_fl == []
    assert answered[0]["answer"] == "Authorized to work in the US: Yes"
    assert answered[1]["answer"] == "Target base salary: 140000"


def test_one_question_can_take_two_answers():
    answered, _ = answer_questions(
        ["Are you legally authorized to work in the US / will you require sponsorship?"],
        PROFILE.applicant,
        RULES,
    )
    assert "Authorized to work in the US: Yes" in answered[0]["answer"]
    assert "Needs sponsorship now: No" in answered[0]["answer"]


@pytest.mark.parametrize(
    "question",
    [
        "Do you have 5+ years of data engineering experience?",
        "Do you have experience with Power BI or Tableau?",
        "Do you have a Bachelor's degree in Computer Science?",
        # An answerable word doesn't make an experience claim safe to answer.
        "Do you have 3 years of experience working with visa data?",
        "What is your favorite data tool?",
    ],
)
def test_experience_claims_and_unknown_questions_are_left_for_fl(question):
    answered, for_fl = answer_questions([question], PROFILE.applicant, RULES)
    assert answered == []
    assert for_fl == [question]


def test_a_real_profile_answer_changes_with_the_profile():
    applicant = copy.deepcopy(PROFILE.applicant)
    applicant["work_authorization"]["needs_sponsorship_now"] = True
    answered, _ = answer_questions(["Do you require visa sponsorship?"], applicant, RULES)
    assert "Needs sponsorship now: Yes" in answered[0]["answer"]


# ---------------------------------------------------------------- page and pack


def row(number=1, status="awaiting_approval", sample=True, **snapshot):
    snap = {
        "company": "Acme",
        "title": "Data Engineer",
        "url": "https://jobs.lever.co/a/1",
        "site": "no_account",
        "score": 60,
        "decision": "apply",
        "work_mode": "remote",
        "location": "US",
        "gaps": ["Kafka"],
        "nice_missing": [],
        "seven_second": "A data engineer",
        "resume_status": "ready",
        "problems": [],
        "pdf": "C:/x/Alex_DE_Acme.pdf",
        "review_page": "C:/x/review.html",
        "cost_usd": 0.2,
        "questions": ["Are you authorized to work in the US?", "Do you have 5+ years of SQL?"],
        **snapshot,
    }
    return {
        "number": number,
        "posting_version_id": number,
        "sample": sample,
        "status": status,
        "reason": None,
        "snapshot": snap,
    }


def page(rows, skipped=(), pack=None):
    from pathlib import Path

    return queue_page(rows, list(skipped), TODAY, Path("C:/x"), pack)


def test_a_sample_batch_says_so_loudly():
    assert "绝不能投" in page([row()])
    assert "绝不能投" not in page([row(sample=False)])


def test_page_shows_what_fl_needs_and_escapes_what_it_reads():
    text = page(
        [
            row(
                company="<script>x</script>",
                seven_second="<b>hi</b>",
                gaps=["Kafka"],
                problems=["<i>bad</i>"],
            )
        ]
    )
    assert "<script>x" not in text and "&lt;script&gt;" in text
    assert "<b>hi</b>" not in text and "<i>bad</i>" not in text
    assert "Kafka" in text
    assert "不用账号" in text
    assert "批准 1、3、5" in text


def test_page_lists_what_was_left_out():
    text = page([row()], [(job(9, company="Beta"), "这批已经有这家公司的职位了")])
    assert "Beta" in text and "这家公司" in text


def test_pack_answers_what_it_can_and_asks_about_the_rest():
    text = pack_markdown([row(status="approved")], TODAY, PROFILE.applicant, RULES)
    assert "SAMPLE" in text
    assert "Authorized to work in the US: Yes" in text
    assert "Ask FL, don't guess" in text
    assert "Do you have 5+ years of SQL?" in text
    assert "Never submit without FL's yes" in text
    assert "alex.sample@example.com" in text
    assert "base_salary_floor" not in text  # the floor stays private; forms get the target


def test_pack_for_a_real_profile_has_no_sample_warning():
    text = pack_markdown([row(status="approved", sample=False)], TODAY, PROFILE.applicant, RULES)
    assert "SAMPLE" not in text


def test_a_sample_pack_is_named_so_nobody_can_mistake_it(tmp_path):
    pdf = tmp_path / "Alex_DE_Acme.pdf"
    pdf.write_bytes(b"%PDF")
    pack = write_pack([row(status="approved", pdf=str(pdf))], TODAY, PROFILE, RULES, tmp_path)
    assert pack.name == "SAMPLE_DO_NOT_SUBMIT_submit_pack.md"
    assert pack.parent.name == "SAMPLE_DO_NOT_SUBMIT_submit_pack"
    assert (pack.parent / pdf.name).is_file()


def test_no_approved_jobs_no_pack(tmp_path):
    assert write_pack([row()], TODAY, PROFILE, RULES, tmp_path) is None


def test_the_left_out_list_survives_a_later_update_of_the_page(tmp_path):
    write_page([row()], [(job(9, company="Beta"), "原因")], TODAY, tmp_path, None)
    page_path = write_page([row(status="approved")], [], TODAY, tmp_path, None)
    text = page_path.read_text(encoding="utf-8")
    assert "Beta" in text and "已批准" in text


# ---------------------------------------------------------------- the whole flow, stored


DRAFT = {
    "headline": "Data Engineer · SQL / Python",
    "summary": "Builds data pipelines in SQL and Python.",
    "experience": [
        {
            "where": "quillfeather-bie",
            "bullets": [
                {
                    "text": "Built daily pipelines in Python loading 6 sources into Redshift",
                    "evidence": ["qf-glue-redshift"],
                },
            ],
        }
    ],
    "projects": [
        {
            "where": "bikeshare-pipeline",
            "bullets": [
                {
                    "text": "Built 9 dbt models with 21 tests on PostgreSQL",
                    "evidence": ["bs-dbt-models"],
                },
            ],
        }
    ],
    "skills": ["SQL", "Python", "dbt"],
    "changes": [],
}
REVIEW = {"verdict": "pass", "seven_second_answer": "A data engineer", "edits": [], "notes": []}


def answer(request):
    return DRAFT if request.prompt_name == "resume-tailoring" else REVIEW


@pytest.fixture
def queued_postings(db, greenhouse_jobs):
    """Real postings in the test database, each with a brief the sample can apply to."""
    from psycopg.types.json import Jsonb

    from agents.skills import load_skill
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
    ids_ = [
        r[0]
        for r in db.execute("select posting_version_id from raw.job_postings order by 1").fetchall()
    ]
    version = load_skill("jd-analysis").prompt_version
    for index, posting_version_id in enumerate(ids_):
        call = db.execute(
            "insert into agents.llm_calls (request_hash, prompt_name, prompt_version, model,"
            " served_model, effort, input_hash, output, stop_reason, input_tokens, output_tokens)"
            " values (%s, 'jd-analysis', %s, %s, %s, 'medium', 'h', '{}', 'end_turn', 1, 1)"
            " returning llm_call_id",
            (f"brief{posting_version_id}", version, SETTINGS.model, SETTINGS.model),
        ).fetchone()[0]
        brief = {
            "company": f"Company {index}",
            "title": f"Data Engineer {index}",
            "url": f"https://jobs.lever.co/c{index}/1",
            "archetype": "pipeline_de",
            "work_mode": "remote",
            "board_location": "Remote",
            "hidden_signals": [],
            "seniority": "mid",
            "safety_flags": [],
            "must_haves": [{"skill": "SQL", "weight": "core", "exact_phrases": ["SQL"]}],
            "nice_to_haves": [],
            "knockout_questions_likely": ["Are you authorized to work in the US?"],
        }
        db.execute(
            "insert into agents.jd_briefs (posting_version_id, prompt_version, model,"
            " scope_version, llm_call_id, brief) values (%s, %s, %s, 2, %s, %s)",
            (posting_version_id, version, SETTINGS.model, call, Jsonb(brief)),
        )
    return db


def run_build(db, tmp_path, size=2):
    client = FakeClient(answer=answer)
    results, skipped, failed = build_batch(
        db, client, PROFILE, SAMPLE, SETTINGS, TODAY, RULES, size, tmp_path
    )
    return results, skipped, failed, client


@pytest.mark.db
def test_build_queues_a_batch_and_a_second_run_changes_nothing(queued_postings, tmp_path):
    db = queued_postings
    results, _, failed, _ = run_build(db, tmp_path)
    assert failed == []
    assert len(results) == 2
    rows = batch_rows(db, TODAY)
    assert [(r["number"], r["status"]) for r in rows] == [
        (1, "awaiting_approval"),
        (2, "awaiting_approval"),
    ]
    assert rows[0]["sample"] is True
    assert rows[0]["snapshot"]["site"] == "no_account"
    assert rows[0]["snapshot"]["seven_second"] == "A data engineer"

    again, _, _, client = run_build(db, tmp_path)
    assert again == []
    assert client.requests == []
    assert len(batch_rows(db, TODAY)) == 2


@pytest.mark.db
def test_tomorrows_batch_takes_new_jobs_only(queued_postings, tmp_path):
    db = queued_postings
    run_build(db, tmp_path, size=1)
    today_ids = {r["posting_version_id"] for r in batch_rows(db, TODAY)}
    client = FakeClient(answer=answer)
    tomorrow = date(2026, 11, 5)
    build_batch(db, client, PROFILE, SAMPLE, SETTINGS, tomorrow, RULES, 1, tmp_path)
    tomorrow_ids = {r["posting_version_id"] for r in batch_rows(db, tomorrow)}
    assert tomorrow_ids
    assert not tomorrow_ids & today_ids


@pytest.mark.db
def test_decisions_are_an_event_log_and_steps_cannot_be_skipped(queued_postings, tmp_path):
    db = queued_postings
    run_build(db, tmp_path)
    with pytest.raises(QueueError, match="no job number 9"):
        set_status(db, TODAY, [1, 9], "approved")
    assert batch_rows(db, TODAY)[0]["status"] == "awaiting_approval"  # all or none

    rows = set_status(db, TODAY, [1], "approved")
    assert rows[0]["status"] == "approved"
    rows = set_status(db, TODAY, [1], "passed", "changed my mind")
    assert (rows[0]["status"], rows[0]["reason"]) == ("passed", "changed my mind")
    history = db.execute(
        "select status from agents.application_events where posting_version_id = %s"
        " order by event_id",
        (rows[0]["posting_version_id"],),
    ).fetchall()
    assert [h[0] for h in history] == ["awaiting_approval", "approved", "passed"]
    with pytest.raises(QueueError, match="can't become approved"):
        set_status(db, TODAY, [1], "approved")


@pytest.mark.db
def test_a_job_no_longer_on_its_board_is_not_queued(queued_postings, tmp_path):
    db = queued_postings
    db.execute("update raw.job_sightings set seen_on = %s", (date(2026, 1, 1),))
    results, _, _, _ = run_build(db, tmp_path)
    assert results == []
    assert batch_rows(db, TODAY) == []


@pytest.mark.db
def test_a_fictional_resume_can_never_be_marked_applied(queued_postings, tmp_path):
    db = queued_postings
    run_build(db, tmp_path)
    set_status(db, TODAY, [1], "approved")
    with pytest.raises(QueueError, match="fictional sample profile"):
        set_status(db, TODAY, [1], "applied")
    assert batch_rows(db, TODAY)[0]["status"] == "approved"


@pytest.mark.db
def test_a_real_profile_goes_through_to_applied(queued_postings, tmp_path):
    db = queued_postings
    real = replace(PROFILE, bank=replace(PROFILE.bank, sample=False))
    client = FakeClient(answer=answer)
    build_batch(db, client, real, SAMPLE, SETTINGS, TODAY, RULES, 1, tmp_path)
    with pytest.raises(QueueError, match="can't become applied"):
        set_status(db, TODAY, [1], "applied")  # approval comes first
    set_status(db, TODAY, [1], "approved")
    assert set_status(db, TODAY, [1], "applied")[0]["status"] == "applied"


def test_fit_helpers_still_import():
    # The queue reads scores exactly as fit scoring makes them.
    brief = {
        "must_haves": [{"skill": "SQL", "weight": "core", "exact_phrases": []}],
        "nice_to_haves": [],
    }
    result = score_brief(brief, PROFILE, load_rules(), load_vocabulary(), TODAY)
    assert result.decision != "skip"
