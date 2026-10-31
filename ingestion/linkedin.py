# Adapted from ai-job-search (https://github.com/ai-job-search-dev/ai-job-search),
# .agents/skills/linkedin-search/cli/src/helpers.ts (extractDivContent, parseJobCards,
# parseJobDetail) and url-reference.md at commit 83c788d.
# Copyright (c) 2026 Mads Lorentzen. MIT License; full text in LICENSES/ai-job-search-MIT.txt
#
# Changes from the original: ported from TypeScript to Python; the card and detail parsing follow
# the original regexes. Not ported: the browser-like User-Agent and request headers (we identify
# ourselves honestly, see ingestion/http.py) and the text cleanup of descriptions (we keep the
# description HTML so the safety gate sees hidden markup). Added: a hard per-day request budget.
"""LinkedIn public (logged-out) job listings. OFF by default (decision #6, #24).

Automated access is against LinkedIn's terms, so: personal use, low volume, only the public
jobs-guest pages, never a logged-in account, no disguise. Turned on by LINKEDIN_PUBLIC_ENABLED=true;
every request counts against LINKEDIN_MAX_REQUESTS_PER_DAY (a hard cap across all runs of a day).
Jobs already stored are not fetched again, which keeps the budget for new ones. If LinkedIn
blocks us, the run records the error and stops; there is no workaround by design.

Raw payload = the HTML LinkedIn returned (the search card and the detail page); fields are parsed
from it when needed, so a better parser can re-read old postings without fetching again.
"""

import html
import re
from dataclasses import dataclass
from typing import Any

from ingestion.context import BudgetExhausted, FetchContext

NAME = "linkedin"
SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
PAGE_SIZE = 10  # fixed by LinkedIn
PAUSE_SECONDS = 2.0
ENABLED_FLAG = "LINKEDIN_PUBLIC_ENABLED"  # off unless set to true
DAILY_CAP_VARIABLE = "LINKEDIN_MAX_REQUESTS_PER_DAY"
DEFAULT_DAILY_CAP = 50


@dataclass(frozen=True)
class JobCard:
    job_id: str
    title: str
    company: str | None
    location: str | None
    posted: str | None
    card_html: str


@dataclass(frozen=True)
class JobDetail:
    title: str
    company: str | None
    location: str | None
    description_html: str | None
    criteria: dict[str, str]
    is_active: bool


def _clean(fragment: str) -> str:
    """Tag-free, entity-decoded, whitespace-collapsed text of an HTML fragment."""
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def extract_div_content(page: str, class_name: str) -> str | None:
    """Inner HTML of the first <div> with this class, following nested <div>s by depth."""
    opening = re.search(rf'<div[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>', page, re.I)
    if not opening:
        return None
    i, depth = opening.end(), 1
    while depth > 0 and i < len(page):
        next_open = page.find("<div", i)
        next_close = page.find("</div>", i)
        if next_close == -1:
            return None
        if next_open != -1 and next_open < next_close:
            depth, i = depth + 1, next_open + 4
        else:
            depth, i = depth - 1, next_close + 6
    return page[opening.end() : i - 6]


def parse_job_cards(page: str) -> list[JobCard]:
    """The search response is a flat list of <li> cards; split on the job URN so one malformed
    card can't break the rest."""
    cards = []
    for chunk in re.split(r'data-entity-urn="urn:li:jobPosting:', page)[1:]:
        id_match = re.match(r"(\d+)", chunk)
        if not id_match:
            continue
        title = None
        if h3 := re.search(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', chunk, re.I):
            title = _clean(h3.group(1))
        if not title and (sr := re.search(r'class="sr-only"[^>]*>([\s\S]*?)</span>', chunk, re.I)):
            title = _clean(sr.group(1))
        if not title:
            continue
        sub = re.search(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', chunk, re.I)
        loc = re.search(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', chunk, re.I)
        date = re.search(
            r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', chunk, re.I
        )
        cards.append(
            JobCard(
                job_id=id_match.group(1),
                title=title,
                company=_clean(sub.group(1)) or None if sub else None,
                location=_clean(loc.group(1)) or None if loc else None,
                posted=date.group(1) if date else None,
                card_html='data-entity-urn="urn:li:jobPosting:' + chunk,
            )
        )
    return cards


def parse_job_detail(page: str) -> JobDetail:
    title = re.search(
        r'class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)</h[12]>',
        page,
        re.I,
    )
    org = re.search(
        r'class="topcard__org-name-link[^"]*"[^>]*href="[^"]+"[^>]*>([\s\S]*?)</a>', page, re.I
    )
    loc = re.search(
        r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', page, re.I
    )
    description = extract_div_content(page, "show-more-less-html__markup")
    if description is None:
        description = extract_div_content(page, "description__text")
    criteria = {
        _clean(label).lower(): _clean(value)
        for label, value in re.findall(
            r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?'
            r'class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>',
            page,
            re.I,
        )
    }
    # A closed posting shows a banner in the top card; look only above the description, since
    # recruiter text can quote the same phrase. No banner means "no banner found", not "open".
    start = re.search(r'class="(?:show-more-less-html__markup|description__text)', page, re.I)
    top_card = page if start is None else page[: start.start()]
    closed = re.search(r"closed-job__flavor|no longer accepting applications", top_card, re.I)
    return JobDetail(
        title=_clean(title.group(1)) if title else "(untitled)",
        company=_clean(org.group(1)) or None if org else None,
        location=_clean(loc.group(1)) or None if loc else None,
        description_html=description,
        criteria=criteria,
        is_active=closed is None,
    )


def _company_slug(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "unknown").lower()).strip("-") or "unknown"


def _search_params(options: dict[str, Any], start: int) -> list[tuple[str, str]]:
    params = [("keywords", options["keywords"]), ("location", options["location"])]
    if options.get("posted_within_days"):
        params.append(("f_TPR", f"r{int(options['posted_within_days']) * 86400}"))
    work_type = {"onsite": "1", "remote": "2", "hybrid": "3"}.get(options.get("work_mode", ""))
    if work_type:
        params.append(("f_WT", work_type))
    params.append(("start", str(start)))
    return params


def fetch_jobs(ctx: FetchContext, target: str) -> list[dict[str, Any]]:
    """Search pages, then a detail page for each job not already stored, until the search runs
    out, `max_pages` is reached, or the request budget is used up (then stop and keep what we
    have)."""
    jobs: list[dict[str, Any]] = []
    try:
        for page in range(int(ctx.options.get("max_pages", 3))):
            if page:
                ctx.sleep(PAUSE_SECONDS)
            cards = parse_job_cards(
                ctx.get_text(SEARCH_URL, _search_params(ctx.options, page * PAGE_SIZE))
            )
            if not cards:
                break
            for card in cards:
                if card.job_id in ctx.known_job_ids:
                    ctx.seen_only.append((_company_slug(card.company), card.job_id))
                    continue
                ctx.sleep(PAUSE_SECONDS)
                detail_html = ctx.get_text(DETAIL_URL.format(job_id=card.job_id))
                jobs.append(
                    {"job_id": card.job_id, "card_html": card.card_html, "detail_html": detail_html}
                )
    except BudgetExhausted:
        pass  # ctx.budget_exhausted is set; the run records it and tomorrow continues
    return jobs


def job_id(job: dict[str, Any]) -> str:
    return str(job["job_id"])


def _card(job: dict[str, Any]) -> JobCard | None:
    cards = parse_job_cards(job.get("card_html") or "")
    return cards[0] if cards else None


def company(job: dict[str, Any], target: str) -> str:
    """The company named on the search card, which is also what a later card shows for a
    seen-only job, so its sighting lands on the same key."""
    card = _card(job)
    return _company_slug(card.company if card else None)


def posting_html(job: dict[str, Any]) -> str:
    detail = parse_job_detail(job.get("detail_html") or "")
    return f"<h1>{html.escape(detail.title)}</h1>\n{detail.description_html or ''}"


def content_fields(job: dict[str, Any]) -> dict[str, Any]:
    """What the posting says, parsed from the detail page (not the card's relative date)."""
    detail = parse_job_detail(job.get("detail_html") or "")
    return {
        "title": detail.title,
        "company": detail.company,
        "location": detail.location,
        "description": detail.description_html,
        "criteria": detail.criteria,
    }
