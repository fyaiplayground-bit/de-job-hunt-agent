"""Settings for the pipeline, read from environment variables (and `.env` when present).

Every other module gets its settings from `load_settings()` instead of reading os.environ
itself, so there is one place that knows which variables exist and what their defaults are.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """A required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str

    def postgres_conninfo(self) -> str:
        """Connection string for psycopg. Not for logging: it contains the password."""
        return (
            f"host={self.postgres_host} port={self.postgres_port} dbname={self.postgres_db} "
            f"user={self.postgres_user} password={self.postgres_password}"
        )


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


# Sources that stay off unless explicitly turned on, and the variable that turns them on.
OFF_BY_DEFAULT = {"linkedin": "LINKEDIN_PUBLIC_ENABLED"}


def is_source_enabled(source: str) -> bool:
    """`<SOURCE>_ENABLED` from the environment (e.g. GREENHOUSE_ENABLED): on unless set to false.
    LinkedIn is the exception: off unless LINKEDIN_PUBLIC_ENABLED is set to true (decision #6).

    Call after load_settings() so values from .env are already in the environment.
    """
    if source in OFF_BY_DEFAULT:
        value = os.environ.get(OFF_BY_DEFAULT[source], "false").strip().lower()
        return value in {"true", "1", "yes", "on"}
    value = os.environ.get(f"{source.upper()}_ENABLED", "true").strip().lower()
    return value not in {"false", "0", "no", "off"}


def load_settings(env_file: str | None = ".env") -> Settings:
    """Read settings. Values already in the environment win over the file.

    Pass env_file=None to read only the real environment (used by tests).
    """
    if env_file is not None:
        load_dotenv(env_file, override=False)

    port_text = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ConfigError(f"POSTGRES_PORT must be a number, got {port_text!r}.") from exc

    return Settings(
        postgres_host=os.environ.get("POSTGRES_HOST", "127.0.0.1").strip() or "127.0.0.1",
        postgres_port=port,
        postgres_db=_required("POSTGRES_DB"),
        postgres_user=_required("POSTGRES_USER"),
        postgres_password=_required("POSTGRES_PASSWORD"),
    )
