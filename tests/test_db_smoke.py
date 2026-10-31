"""Smoke test: the real settings from .env reach the local Postgres and it answers.

Skipped (not failed) when Postgres isn't running, so the rest of the suite still works with
Docker Desktop closed.
"""

import psycopg
import pytest

from pipeline.config import load_settings


@pytest.mark.db
def test_can_query_local_postgres():
    settings = load_settings()
    try:
        conn = psycopg.connect(settings.postgres_conninfo(), connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running (open Docker Desktop to run this test)")

    with conn:
        row = conn.execute("select current_database(), version()").fetchone()

    assert row[0] == settings.postgres_db
    assert row[1].startswith("PostgreSQL 17")
