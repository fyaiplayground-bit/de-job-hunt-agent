"""Shared test helpers: sample API responses, and a throwaway test database."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from pipeline.config import load_settings
from pipeline.db import connect, migrate

FIXTURES = Path(__file__).parent / "fixtures"
TEST_DB = "jobhunt_test"


@pytest.fixture
def greenhouse_jobs() -> list[dict]:
    """Fresh copy each time, so a test can edit jobs without affecting other tests."""
    data = json.loads((FIXTURES / "greenhouse_jobs.json").read_text(encoding="utf-8"))
    return copy.deepcopy(data["jobs"])


@pytest.fixture
def lever_postings() -> list[dict]:
    return json.loads((FIXTURES / "lever_postings.json").read_text(encoding="utf-8"))


@pytest.fixture
def db():
    """A connection to the separate jobhunt_test database, freshly migrated for each test.

    Never the real database: the name is fixed and checked. Skipped when Postgres is down.
    """
    settings = load_settings()
    assert settings.postgres_db != TEST_DB, "the real database must not be the test database"
    try:
        admin = psycopg.connect(settings.postgres_conninfo(), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running (open Docker Desktop to run this test)")
    with admin:
        exists = admin.execute(
            "select 1 from pg_database where datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            admin.execute(sql.SQL("create database {}").format(sql.Identifier(TEST_DB)))

    conn = connect(replace(settings, postgres_db=TEST_DB))
    conn.execute("drop schema if exists gate cascade")
    conn.execute("drop schema if exists raw cascade")
    conn.execute("drop table if exists public.schema_migrations")
    migrate(conn)
    yield conn
    conn.close()
