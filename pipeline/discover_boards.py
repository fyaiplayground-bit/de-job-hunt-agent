"""List Greenhouse and Lever boards that freehire has shown us but config/companies.toml lacks.

    uv run python -m pipeline.discover_boards            # top 40 by number of jobs seen
    uv run python -m pipeline.discover_boards --limit 100

Read-only: it suggests, FL picks, and a board is added to companies.toml by hand (decision #24).
Fetching a board directly gets every job on it, not just the ones a freehire search matched.
"""

import argparse
import sys
import tomllib

import psycopg

from pipeline.db import connect
from pipeline.ingest import COMPANIES_FILE


def configured_boards() -> set[tuple[str, str]]:
    with COMPANIES_FILE.open("rb") as f:
        config = tomllib.load(f)
    return {
        (source, token.lower())
        for source, section in config.items()
        for token in section.get("boards", [])
    }


def candidate_boards(conn: psycopg.Connection, limit: int) -> list[tuple]:
    """(ats, board token, company, jobs seen, newest posted_at) for boards found via freehire."""
    rows = conn.execute(
        "select payload->>'source', lower(split_part(payload->>'external_id', ':', 1)),"
        "  min(payload->>'company'), count(distinct source_job_id),"
        "  max(payload->>'posted_at')"
        " from raw.job_postings"
        " where source = 'freehire' and payload->>'source' in ('greenhouse', 'lever')"
        "   and payload->>'external_id' like '%%:%%'"
        " group by 1, 2 order by 4 desc, 2"
    ).fetchall()
    known = configured_boards()
    return [row for row in rows if (row[0], row[1]) not in known][:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Suggest job boards to add.")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    with connect() as conn:
        rows = candidate_boards(conn, args.limit)
    if not rows:
        print("no new boards found (run the freehire ingestion first)")
    print(f"{'ats':10} {'board token':32} {'jobs':>4}  {'newest':10}  company")
    for ats, token, company, jobs, newest in rows:
        print(f"{ats:10} {token:32} {jobs:4}  {(newest or '')[:10]:10}  {company}")
    print("\nto add one: put its token under [greenhouse] or [lever] in config/companies.toml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
