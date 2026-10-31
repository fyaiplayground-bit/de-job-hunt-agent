"""Unit tests for the LinkedIn source: parsing, the request budget, known jobs, off by default.
No network: every response comes from the synthetic fixtures."""

import httpx
import pytest

from ingestion import linkedin
from ingestion.context import FetchContext
from ingestion.http import USER_AGENT, make_client
from pipeline.config import is_source_enabled
from pipeline.safety_gate import run_gate

SEARCH = {"keywords": "data engineer", "location": "United States", "max_pages": 1}


@pytest.fixture
def search_html(request):
    return (request.path.parent / "fixtures" / "linkedin_search.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html(request):
    return (request.path.parent / "fixtures" / "linkedin_detail.html").read_text(encoding="utf-8")


def site(search_html: str, detail_html: str, seen: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "seeMoreJobPostings" in request.url.path:
            page = search_html if request.url.params["start"] == "0" else ""
            return httpx.Response(200, text=page)
        return httpx.Response(200, text=detail_html)

    return make_client(transport=httpx.MockTransport(handler))


def test_cards_are_parsed_and_a_malformed_card_is_skipped(search_html):
    cards = linkedin.parse_job_cards(search_html)

    assert [c.job_id for c in cards] == ["4001001001", "4001001002", "4001001003"]
    first = cards[0]
    assert (first.title, first.company, first.location, first.posted) == (
        "Data Engineer",
        "Example Data Co",
        "New York, NY",
        "2026-10-30",
    )
    assert cards[1].company == "Small Co & Partners"  # entities decoded


def test_detail_keeps_the_description_html_so_the_gate_sees_hidden_text(detail_html):
    detail = linkedin.parse_job_detail(detail_html)

    assert (detail.title, detail.company, detail.location) == (
        "Data Engineer",
        "Example Data Co",
        "New York, NY",
    )
    assert detail.criteria == {
        "seniority level": "Mid-Senior level",
        "employment type": "Full-time",
    }
    assert detail.is_active
    assert "display:none" in detail.description_html

    result = run_gate(linkedin.posting_html({"detail_html": detail_html}), "html")
    assert result.triage == "block"
    assert "Ignore all previous" not in result.cleaned_text


def test_closed_banner_in_the_top_card_marks_the_job_inactive(detail_html):
    closed = detail_html.replace(
        '<section class="description">',
        '<figure class="closed-job closed-job__flavor">No longer accepting applications</figure>'
        '<section class="description">',
    )
    assert not linkedin.parse_job_detail(closed).is_active


def test_fetch_gets_details_for_new_jobs_and_identifies_honestly(search_html, detail_html):
    seen = []
    ctx = FetchContext(site(search_html, detail_html, seen), options=SEARCH, sleep=lambda _: None)

    jobs = linkedin.fetch_jobs(ctx, "us-data-engineer")

    assert [j["job_id"] for j in jobs] == ["4001001001", "4001001002", "4001001003"]
    assert ctx.requests_made == 4  # 1 search page + 3 details
    assert all(r.headers["User-Agent"] == USER_AGENT for r in seen)
    assert seen[0].url.params["keywords"] == "data engineer"


def test_the_request_budget_is_a_hard_stop(search_html, detail_html):
    seen = []
    ctx = FetchContext(
        site(search_html, detail_html, seen), options=SEARCH, request_budget=3, sleep=lambda _: None
    )

    jobs = linkedin.fetch_jobs(ctx, "us-data-engineer")

    assert len(seen) == 3 and ctx.requests_made == 3
    assert len(jobs) == 2  # 1 search + 2 details, then stop
    assert ctx.budget_exhausted


def test_known_jobs_are_not_fetched_again_but_still_count_as_seen(search_html, detail_html):
    seen = []
    ctx = FetchContext(
        site(search_html, detail_html, seen),
        options=SEARCH,
        known_job_ids=frozenset({"4001001001", "4001001003"}),
        sleep=lambda _: None,
    )

    jobs = linkedin.fetch_jobs(ctx, "us-data-engineer")

    assert [j["job_id"] for j in jobs] == ["4001001002"]
    assert ctx.seen_only == [("example-data-co", "4001001001"), ("big-retail", "4001001003")]
    assert ctx.requests_made == 2


def test_company_of_a_stored_job_matches_a_seen_only_card(search_html, detail_html):
    card = linkedin.parse_job_cards(search_html)[0]
    job = {"job_id": card.job_id, "card_html": card.card_html, "detail_html": detail_html}

    assert linkedin.company(job, "s") == "example-data-co"


def test_linkedin_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("LINKEDIN_PUBLIC_ENABLED", raising=False)
    assert not is_source_enabled("linkedin")
    monkeypatch.setenv("LINKEDIN_PUBLIC_ENABLED", "false")
    assert not is_source_enabled("linkedin")
    monkeypatch.setenv("LINKEDIN_PUBLIC_ENABLED", "true")
    assert is_source_enabled("linkedin")
