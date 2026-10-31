# Adapted from ai-job-search (https://github.com/ai-job-search-dev/ai-job-search),
# .agents/skills/freehire-search/cli/src/commands/search.ts and url-reference.md at commit 83c788d.
# Copyright (c) 2026 Mads Lorentzen. MIT License; full text in LICENSES/ai-job-search-MIT.txt
#
# Changes from the original: ported from TypeScript to Python; keeps the endpoint, the query and
# facet parameters, the response envelope and the offset + limit <= 10000 paging guard; requests
# go through our ingestion/http.py (honest User-Agent, Retry-After, backoff) via FetchContext.
"""freehire.me: one aggregator search covers jobs from ~50 ATSs (Greenhouse, Workday, Ashby, ...).

A search source, not a board source: each target is a saved search in config/searches.toml, and
the company comes from each job. API reference: reference/ai-job-search/.agents/skills/
freehire-search/url-reference.md (the search endpoint returns full descriptions).
"""

import html
import re
from typing import Any

from ingestion.context import FetchContext

NAME = "freehire"
SEARCH_URL = "https://freehire.me/api/v1/agent/jobs/search"
MAX_WINDOW = 10_000  # the API refuses offset + limit beyond this
PAUSE_BETWEEN_PAGES_SECONDS = 1.0


def _search_params(options: dict[str, Any]) -> list[tuple[str, str]]:
    """Query parameters for one saved search. Facets like countries repeat the key (ORed)."""
    params = [("q", options["query"]), ("description_format", "html")]
    if options.get("posted_within_days"):
        params.append(("posted_within_days", str(options["posted_within_days"])))
    for facet in ("countries", "regions", "cities", "seniority", "category", "skills"):
        params.extend((facet, str(value)) for value in options.get(facet, []))
    if options.get("work_mode"):
        params.append(("work_mode", options["work_mode"]))
    return params


def fetch_jobs(ctx: FetchContext, target: str) -> list[dict[str, Any]]:
    """Every job matching the saved search, page by page, up to `max_pages`."""
    page_size = int(ctx.options.get("page_size", 100))
    max_pages = int(ctx.options.get("max_pages", 20))
    base = _search_params(ctx.options)
    jobs: list[dict[str, Any]] = []
    for page in range(max_pages):
        offset = page * page_size
        if offset + page_size > MAX_WINDOW:
            break
        if page:
            ctx.sleep(PAUSE_BETWEEN_PAGES_SECONDS)
        body = ctx.get_json(SEARCH_URL, [*base, ("limit", str(page_size)), ("offset", str(offset))])
        page_jobs = body.get("data") or []
        jobs.extend(page_jobs)
        if len(page_jobs) < page_size:
            break
    return jobs


def job_id(job: dict[str, Any]) -> str:
    """freehire's stable public id (its internal numeric id is never exposed)."""
    return str(job["public_slug"])


def company(job: dict[str, Any], target: str) -> str:
    """Search sources: the company comes from the job itself."""
    if job.get("company_slug"):
        return str(job["company_slug"])
    return re.sub(r"[^a-z0-9]+", "-", (job.get("company") or "unknown").lower()).strip("-")


def posting_html(job: dict[str, Any]) -> str:
    """Title + description as HTML, the text the safety gate checks."""
    return f"<h1>{html.escape(job.get('title') or '')}</h1>\n{job.get('description') or ''}"


def content_fields(job: dict[str, Any]) -> dict[str, Any]:
    """What the posting says. Excludes freehire's own changing fields: view/apply/vote counts,
    last_seen_at, updated_at, the `reality` scores, enrichment and the utm-tagged URL."""
    return {
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "work_mode": job.get("work_mode"),
        "description": job.get("description"),
        "ats": job.get("source"),
        "external_id": job.get("external_id"),
    }
