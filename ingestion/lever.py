"""Lever public postings API: one call returns every published posting for a company.

Docs: https://github.com/lever/postings-api
"""

import html
from typing import Any

import httpx

from ingestion.http import get_json

NAME = "lever"
POSTINGS_URL = "https://api.lever.co/v0/postings/{token}"


def fetch_jobs(client: httpx.Client, token: str) -> list[dict[str, Any]]:
    """All published postings for the company."""
    return get_json(client, POSTINGS_URL.format(token=token), {"mode": "json"})


def job_id(job: dict[str, Any]) -> str:
    return str(job["id"])


def posting_html(job: dict[str, Any]) -> str:
    """Title + description as HTML, the text the safety gate checks.

    Lever splits a posting into `description`, a list of titled sections (`lists`, e.g.
    "Requirements") and `additional` (often compensation); they are joined in page order.
    """
    parts = [f"<h1>{html.escape(job.get('text') or '')}</h1>", job.get("description") or ""]
    for section in job.get("lists") or []:
        parts.append(f"<h3>{html.escape(section.get('text') or '')}</h3>")
        parts.append(f"<ul>{section.get('content') or ''}</ul>")
    parts.append(job.get("additional") or "")
    return "\n".join(parts)


def content_fields(job: dict[str, Any]) -> dict[str, Any]:
    """The fields that define what the posting says (see greenhouse.content_fields)."""
    return {
        "title": job.get("text"),
        "categories": job.get("categories"),
        "workplace_type": job.get("workplaceType"),
        "description": job.get("description"),
        "lists": job.get("lists"),
        "additional": job.get("additional"),
    }
