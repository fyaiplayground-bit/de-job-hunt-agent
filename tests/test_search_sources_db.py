"""Search sources against the jobhunt_test database: freehire and LinkedIn runs, the per-day
LinkedIn cap across runs, cross-source dedupe, and board discovery."""

import httpx
import pytest

from ingestion.http import make_client
from pipeline.discover_boards import candidate_boards
from pipeline.ingest import Target, ingest_target, read_targets, select_targets

pytestmark = pytest.mark.db

FREEHIRE = Target(
    "freehire",
    "us-data-engineering",
    {"query": "title:data engineer", "countries": ["us"], "posted_within_days": 2},
)
LINKEDIN = Target(
    "linkedin",
    "us-data-engineer",
    {"keywords": "data engineer", "location": "United States", "max_pages": 1},
)


def client_for(routes: dict[str, httpx.Response | str]) -> httpx.Client:
    """Answers by URL path prefix; JSON for dict/list bodies, text for strings, else 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, body in routes.items():
            if request.url.path.startswith(prefix):
                if isinstance(body, str):
                    return httpx.Response(200, text=body)
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return make_client(transport=httpx.MockTransport(handler))


def no_sleep(_):
    return None


def test_freehire_run_takes_the_company_from_each_job(db, freehire_jobs):
    client = client_for({"/api/v1/agent/jobs/search": {"data": freehire_jobs}})

    result = ingest_target(db, client, FREEHIRE, sleep=no_sleep)

    assert (result.status, result.jobs_seen, result.versions_new, result.requests_made) == (
        "ok",
        3,
        3,
        1,
    )
    companies = [r[0] for r in db.execute("select company from raw.job_postings order by 1")]
    assert companies == ["big-retail", "example-data-co", "small-co"]
    assert db.execute("select target from raw.ingest_runs").fetchone()[0] == "us-data-engineering"


def test_the_same_job_from_greenhouse_and_freehire_is_one_job(db, greenhouse_jobs, freehire_jobs):
    client = client_for(
        {
            "/v1/boards/example/jobs": {"jobs": greenhouse_jobs},
            "/api/v1/agent/jobs/search": {"data": freehire_jobs},
        }
    )
    ingest_target(db, client, Target("greenhouse", "example"), sleep=no_sleep)
    ingest_target(db, client, FREEHIRE, sleep=no_sleep)

    raw_rows = db.execute("select count(*) from raw.job_postings").fetchone()[0]
    jobs = db.execute(
        "select identity_key, chosen_source, sources, copies from dedupe.jobs order by 1"
    ).fetchall()

    assert raw_rows == 5  # 2 greenhouse + 3 freehire, all kept in raw
    assert len(jobs) == 4  # greenhouse 1001 arrived twice
    assert ("greenhouse/example/1001", "greenhouse", ["freehire", "greenhouse"], 2) in jobs
    assert ("freehire:workday/bigretail:R12345", "freehire", ["freehire"], 1) in [
        tuple(j) for j in jobs
    ]


def test_linkedin_second_run_only_records_sightings(db, request):
    fixtures = request.path.parent / "fixtures"
    routes = {
        "/jobs-guest/jobs/api/seeMoreJobPostings": (fixtures / "linkedin_search.html").read_text(
            encoding="utf-8"
        ),
        "/jobs-guest/jobs/api/jobPosting": (fixtures / "linkedin_detail.html").read_text(
            encoding="utf-8"
        ),
    }
    first = ingest_target(db, client_for(routes), LINKEDIN, sleep=no_sleep)
    second = ingest_target(db, client_for(routes), LINKEDIN, sleep=no_sleep)

    assert (first.versions_new, first.requests_made) == (3, 4)
    assert (second.versions_new, second.requests_made, second.jobs_seen) == (0, 1, 3)


def test_linkedin_daily_cap_holds_across_runs(db, request, monkeypatch):
    monkeypatch.setenv("LINKEDIN_MAX_REQUESTS_PER_DAY", "3")
    fixtures = request.path.parent / "fixtures"
    routes = {
        "/jobs-guest/jobs/api/seeMoreJobPostings": (fixtures / "linkedin_search.html").read_text(
            encoding="utf-8"
        ),
        "/jobs-guest/jobs/api/jobPosting": (fixtures / "linkedin_detail.html").read_text(
            encoding="utf-8"
        ),
    }

    first = ingest_target(db, client_for(routes), LINKEDIN, sleep=no_sleep)
    second = ingest_target(db, client_for(routes), LINKEDIN, sleep=no_sleep)

    assert (first.requests_made, first.versions_new) == (3, 2)
    assert "budget" in first.note
    assert second.requests_made == 0 and "budget" in second.note
    total = db.execute(
        "select sum(requests_made) from raw.ingest_runs where source = 'linkedin'"
    ).fetchone()[0]
    assert total == 3


def test_discover_boards_lists_new_boards_only(db, freehire_jobs):
    freehire_jobs[1]["external_id"] = "smallco:555"
    freehire_jobs[0]["external_id"] = "reddit:1001"  # reddit is already in companies.toml
    ingest_target(
        db,
        client_for({"/api/v1/agent/jobs/search": {"data": freehire_jobs}}),
        FREEHIRE,
        sleep=no_sleep,
    )

    boards = [(ats, token) for ats, token, *_ in candidate_boards(db, limit=10)]

    assert boards == [("greenhouse", "smallco")]


def test_targets_come_from_both_files_and_linkedin_stays_off(monkeypatch):
    monkeypatch.delenv("LINKEDIN_PUBLIC_ENABLED", raising=False)
    targets = read_targets()

    assert {t.source for t in targets} == {"greenhouse", "lever", "freehire", "linkedin"}
    chosen = select_targets(targets, days=7)
    assert "linkedin" not in {t.source for t in chosen}
    freehire = [t for t in chosen if t.source == "freehire"]
    assert freehire and all(t.options["posted_within_days"] == 7 for t in freehire)
