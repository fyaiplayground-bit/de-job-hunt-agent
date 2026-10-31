"""Greenhouse public job board API: one call returns every open job on a company's board.

Docs: https://developers.greenhouse.io/job-board.html
"""

import html
from typing import Any

import httpx

from ingestion.http import get_json

NAME = "greenhouse"
JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch_jobs(client: httpx.Client, token: str) -> list[dict[str, Any]]:
    """All open jobs on the board, with descriptions (content=true)."""
    data = get_json(client, JOBS_URL.format(token=token), {"content": "true"})
    return data["jobs"]


def job_id(job: dict[str, Any]) -> str:
    return str(job["id"])


def posting_html(job: dict[str, Any]) -> str:
    """Title + description as HTML, the text the safety gate checks.

    Greenhouse sends `content` HTML-escaped (&lt;p&gt;...), so it is unescaped once here.
    """
    title = html.escape(job.get("title") or "")
    return f"<h1>{title}</h1>\n{html.unescape(job.get('content') or '')}"


def content_fields(job: dict[str, Any]) -> dict[str, Any]:
    """The fields that define what the posting says. Excludes updated_at and other fields that
    change without the posting changing, so they don't create a new version every day."""
    return {
        "title": job.get("title"),
        "location": (job.get("location") or {}).get("name"),
        "departments": sorted(d.get("name") or "" for d in job.get("departments") or []),
        "offices": sorted(o.get("name") or "" for o in job.get("offices") or []),
        "content": job.get("content"),
    }
