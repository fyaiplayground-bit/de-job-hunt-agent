"""Settings for the pipeline, read from environment variables (and `.env` when present).

Every other module gets its settings from `load_settings()` instead of reading os.environ
itself, so there is one place that knows which variables exist and what their defaults are.
"""

import os
from dataclasses import dataclass
from pathlib import Path

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


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = "data/sample"


def profile_dir(env_file: str | None = ".env") -> Path:
    """Folder holding the candidate profile (decision #28): PROFILE_DIR, relative to the repo root
    unless absolute. Defaults to the fictional sample; Milestone 5 points it at `private`.

    Reads `.env` itself (no database settings needed). Pass env_file=None in tests.
    """
    if env_file is not None:
        load_dotenv(env_file, override=False)
    folder = Path(os.environ.get("PROFILE_DIR", "").strip() or DEFAULT_PROFILE_DIR)
    return folder if folder.is_absolute() else REPO_ROOT / folder


LLM_EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class LlmSettings:
    """Which Claude model the agents call, and how hard it thinks (decision #30)."""

    model: str
    effort: str


def llm_settings(env_file: str | None = ".env") -> LlmSettings:
    """LLM_MODEL (default claude-opus-5-5) and LLM_EFFORT (default medium) from the environment.
    The API key itself is read by the Anthropic SDK from ANTHROPIC_API_KEY, never by our code.

    Reads `.env` itself (no database settings needed). Pass env_file=None in tests.
    """
    if env_file is not None:
        load_dotenv(env_file, override=False)
    model = os.environ.get("LLM_MODEL", "").strip() or "claude-opus-5-5"
    effort = os.environ.get("LLM_EFFORT", "").strip().lower() or "medium"
    if effort not in LLM_EFFORTS:
        raise ConfigError(f"LLM_EFFORT must be one of {', '.join(LLM_EFFORTS)}, got {effort!r}.")
    return LlmSettings(model=model, effort=effort)


def jd_analysis_settings(env_file: str | None = ".env") -> LlmSettings:
    """The model and effort that brief job postings: JD_ANALYSIS_MODEL and JD_ANALYSIS_EFFORT,
    each falling back to LLM_MODEL / LLM_EFFORT when unset (decision #48). The briefing runs on
    every new posting, so it can use a cheaper model than resume tailoring."""
    base = llm_settings(env_file)
    model = os.environ.get("JD_ANALYSIS_MODEL", "").strip() or base.model
    effort = os.environ.get("JD_ANALYSIS_EFFORT", "").strip().lower() or base.effort
    if effort not in LLM_EFFORTS:
        raise ConfigError(
            f"JD_ANALYSIS_EFFORT must be one of {', '.join(LLM_EFFORTS)}, got {effort!r}."
        )
    return LlmSettings(model=model, effort=effort)


@dataclass(frozen=True)
class DailyAnalysisSettings:
    """jd-analysis inside the daily run (decision #33): on/off and how many new postings a day."""

    enabled: bool
    daily_max: int


def daily_analysis_settings(env_file: str | None = ".env") -> DailyAnalysisSettings:
    """JD_ANALYSIS_ENABLED (default true) and JD_ANALYSIS_DAILY_MAX (default 50)."""
    if env_file is not None:
        load_dotenv(env_file, override=False)
    enabled = os.environ.get("JD_ANALYSIS_ENABLED", "true").strip().lower()
    text = os.environ.get("JD_ANALYSIS_DAILY_MAX", "").strip() or "50"
    try:
        daily_max = int(text)
    except ValueError as exc:
        raise ConfigError(f"JD_ANALYSIS_DAILY_MAX must be a number, got {text!r}.") from exc
    if daily_max < 0:
        raise ConfigError("JD_ANALYSIS_DAILY_MAX can't be negative.")
    return DailyAnalysisSettings(
        enabled=enabled not in {"false", "0", "no", "off"}, daily_max=daily_max
    )


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
