"""Unit tests for the freehire source: paging, parameters, company, change detection. No network."""

import httpx

from ingestion import freehire
from ingestion.context import FetchContext
from ingestion.http import make_client
from pipeline.load import content_hash

SEARCH = {"query": "title:data engineer", "countries": ["us", "ca"], "posted_within_days": 2}


def paged_client(pages: list[list[dict]], seen: list):
    queue = list(pages)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": queue.pop(0), "meta": {}})

    return make_client(transport=httpx.MockTransport(handler))


def test_pages_until_a_short_page_and_pauses_between(freehire_jobs):
    seen, pauses = [], []
    ctx = FetchContext(
        paged_client([freehire_jobs[:2], freehire_jobs[2:]], seen),
        options={**SEARCH, "page_size": 2},
        sleep=pauses.append,
    )

    jobs = freehire.fetch_jobs(ctx, "us-data-engineering")

    assert len(jobs) == 3
    assert ctx.requests_made == 2
    assert pauses == [freehire.PAUSE_BETWEEN_PAGES_SECONDS]
    assert [r.url.params["offset"] for r in seen] == ["0", "2"]


def test_query_repeats_facets_and_asks_for_html(freehire_jobs):
    seen = []
    ctx = FetchContext(paged_client([[]], seen), options=SEARCH, sleep=lambda _: None)

    freehire.fetch_jobs(ctx, "s")

    params = seen[0].url.params
    assert params.get_list("countries") == ["us", "ca"]
    assert params["description_format"] == "html"
    assert params["posted_within_days"] == "2"


def test_stops_at_max_pages_and_at_the_api_window(freehire_jobs):
    seen = []
    full = [freehire_jobs[0]] * 2
    ctx = FetchContext(
        paged_client([full] * 10, seen),
        options={**SEARCH, "page_size": 2, "max_pages": 3},
        sleep=lambda _: None,
    )
    freehire.fetch_jobs(ctx, "s")
    assert len(seen) == 3

    seen.clear()
    window = FetchContext(
        paged_client([full] * 10, seen),
        options={**SEARCH, "page_size": 6000, "max_pages": 5},
        sleep=lambda _: None,
    )
    freehire.fetch_jobs(window, "s")
    assert len(seen) == 1  # a second page would need offset 6000 + 6000 > 10000


def test_company_comes_from_the_job_not_the_search(freehire_jobs):
    assert freehire.company(freehire_jobs[0], "us-data-engineering") == "example-data-co"
    assert freehire.company({"company": "Acme, Inc."}, "s") == "acme-inc"


def test_counters_and_reality_scores_do_not_create_versions(freehire_jobs):
    job = freehire_jobs[0]
    before = content_hash(freehire.content_fields(job))
    job.update(view_count=999, last_seen_at="2026-11-30T00:00:00Z", reality={"class": "stale"})
    job["url"] = job["url"].replace("utm_source=freehire.me", "utm_source=other")

    assert content_hash(freehire.content_fields(job)) == before


def test_posting_html_has_title_and_description(freehire_jobs):
    page = freehire.posting_html(freehire_jobs[0])

    assert page.startswith("<h1>Data Engineer</h1>")
    assert "<strong>Python</strong>" in page
