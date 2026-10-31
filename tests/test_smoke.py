"""Smoke tests: settings load correctly, and the local Postgres answers.

The database test is skipped (not failed) when Postgres isn't running, so the rest of the
suite still works with Docker Desktop closed.
"""

import psycopg
import pytest

from pipeline.config import ConfigError, load_settings

DB_VARS = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


@pytest.fixture
def clean_env(monkeypatch):
    for name in DB_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_settings_read_from_environment(clean_env):
    clean_env.setenv("POSTGRES_DB", "testdb")
    clean_env.setenv("POSTGRES_USER", "tester")
    clean_env.setenv("POSTGRES_PASSWORD", "secret")
    clean_env.setenv("POSTGRES_PORT", "6543")

    settings = load_settings(env_file=None)

    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 6543
    assert settings.postgres_db == "testdb"
    assert "password=secret" in settings.postgres_conninfo()


def test_missing_password_gives_clear_error(clean_env):
    clean_env.setenv("POSTGRES_DB", "testdb")
    clean_env.setenv("POSTGRES_USER", "tester")

    with pytest.raises(ConfigError, match="POSTGRES_PASSWORD"):
        load_settings(env_file=None)


def test_bad_port_gives_clear_error(clean_env):
    clean_env.setenv("POSTGRES_DB", "testdb")
    clean_env.setenv("POSTGRES_USER", "tester")
    clean_env.setenv("POSTGRES_PASSWORD", "secret")
    clean_env.setenv("POSTGRES_PORT", "abc")

    with pytest.raises(ConfigError, match="POSTGRES_PORT"):
        load_settings(env_file=None)


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
