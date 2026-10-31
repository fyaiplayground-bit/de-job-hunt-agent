"""Load fetched jobs into the raw layer, idempotently.

For each job: store a new version only if its content changed (content_hash), and record that
it was seen today. Running the same day twice adds nothing; a changed posting adds one version.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from ingestion.sources import get_source


@dataclass(frozen=True)
class LoadCounts:
    jobs_seen: int
    versions_new: int
    sightings_new: int


def content_hash(fields: dict[str, Any]) -> str:
    """Stable fingerprint of a posting's content: same fields in, same hash out."""
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_jobs(
    conn: psycopg.Connection,
    source: str,
    company: str,
    jobs: list[dict[str, Any]],
    run_id: UUID,
    fetched_at: datetime,
) -> LoadCounts:
    """Write one board's jobs in a single transaction: all of them or none."""
    module = get_source(source)
    versions_new = sightings_new = 0
    with conn.transaction():
        for job in jobs:
            source_job_id = module.job_id(job)
            inserted = conn.execute(
                "insert into raw.job_postings"
                " (source, company, source_job_id, content_hash, payload, fetched_at, run_id)"
                " values (%s, %s, %s, %s, %s, %s, %s)"
                " on conflict (source, company, source_job_id, content_hash) do nothing",
                (
                    source,
                    company,
                    source_job_id,
                    content_hash(module.content_fields(job)),
                    Jsonb(job),
                    fetched_at,
                    run_id,
                ),
            )
            versions_new += inserted.rowcount
            seen = conn.execute(
                "insert into raw.job_sightings (source, company, source_job_id, seen_on, run_id)"
                " values (%s, %s, %s, %s, %s)"
                " on conflict do nothing",
                (source, company, source_job_id, fetched_at.date(), run_id),
            )
            sightings_new += seen.rowcount
    return LoadCounts(jobs_seen=len(jobs), versions_new=versions_new, sightings_new=sightings_new)
