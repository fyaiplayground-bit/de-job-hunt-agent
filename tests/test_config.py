"""Unit tests for pipeline/config.py: settings are read from the environment with clear errors.

These use fake environment variables and never touch a real database.
"""

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

    assert settings.postgres_host == "127.0.0.1"
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
