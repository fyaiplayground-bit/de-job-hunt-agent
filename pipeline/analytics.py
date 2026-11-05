"""Rebuild the analytics layer with dbt (decision #41).

    uv run python -m pipeline.analytics                # sync, then build and test every model
    uv run python -m pipeline.analytics docs           # also write the lineage docs to dbt/target

The pipeline's own tables are never touched: dbt reads raw, gate, dedupe, agents and ops, and builds
into the analytics_* schemas, which can be dropped and rebuilt at any time. Two things are copied
in first: the vocabulary's synonyms as a seed, and the profile's skills as a table.
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

from agents.fit_scoring import _resolve, load_vocabulary, profile_fingerprint
from agents.profile import load_profile
from pipeline.config import REPO_ROOT, load_settings, profile_dir

DBT_DIR = REPO_ROOT / "dbt"
SYNONYMS_SEED = DBT_DIR / "seeds" / "skill_synonyms.csv"


def write_synonyms_seed(path: Path = SYNONYMS_SEED) -> None:
    """The vocabulary's synonyms as a dbt seed. Generated, so config/skill_vocabulary.toml stays
    the one place they are edited."""
    vocabulary = load_vocabulary()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="\n", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["wording_key", "canonical"])
        writer.writerows(sorted(vocabulary.synonyms.items()))


def sync_profile_skills(conn: psycopg.Connection, folder: Path | None = None) -> int:
    """Replace agents.profile_skills with every wording that leads to a profile skill, resolved
    the way fit scoring resolves names, so dbt and the scorer agree on what the profile has."""
    folder = folder or profile_dir()
    bank = load_profile(folder).bank
    vocabulary = load_vocabulary()
    fingerprint = profile_fingerprint(folder)
    terms = [term for skill in bank.skills for term in (skill.name, *skill.aliases)]
    terms += [*vocabulary.synonyms, *vocabulary.families]
    rows: dict[str, tuple[str, str, str, str | None, str]] = {}
    for term in terms:
        names = _resolve(term, bank, vocabulary)[0]
        found = [skill for skill in bank.skills if skill.name in names]
        if not found:
            continue
        # A family counts as "have" as soon as one member does.
        best = next((skill for skill in found if skill.status == "have"), found[0])
        key = term.strip().lower()
        rows.setdefault(
            key, (key, best.name, best.status, bank.skill_level(best.name), fingerprint)
        )
    with conn.transaction():
        conn.execute("delete from agents.profile_skills")
        with conn.cursor() as cursor:
            cursor.executemany(
                "insert into agents.profile_skills"
                " (term_key, skill, status, level, profile_fingerprint)"
                " values (%s, %s, %s, %s, %s)",
                list(rows.values()),
            )
    return len(rows)


@dataclass(frozen=True)
class DbtResult:
    ok: bool
    passed: int
    failed: list[str]
    error: str | None = None


def run_dbt(command: tuple[str, ...] = ("build",), variables: str | None = None) -> DbtResult:
    """Run dbt in this process. Connection settings come from the environment, loaded from .env."""
    from dbt.cli.main import dbtRunner

    load_settings()
    args = [*command, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--quiet"]
    if variables:
        args += ["--vars", variables]
    result = dbtRunner().invoke(args)
    if result.exception is not None:
        return DbtResult(False, 0, [], str(result.exception))
    nodes = list(getattr(result.result, "results", None) or [])
    failed = [
        f"{node.node.name}: {node.status}"
        for node in nodes
        if str(node.status) in ("error", "fail", "runtime error")
    ]
    return DbtResult(bool(result.success), len(nodes) - len(failed), failed)


def refresh(conn: psycopg.Connection, folder: Path | None = None) -> DbtResult:
    """Everything an analytics run needs: copy the two inputs, then build and test."""
    write_synonyms_seed()
    sync_profile_skills(conn, folder)
    return run_dbt()


def main(argv: list[str] | None = None) -> int:
    from pipeline.db import connect, migrate

    parser = argparse.ArgumentParser(prog="python -m pipeline.analytics")
    parser.add_argument("command", nargs="?", choices=("build", "docs"), default="build")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    with connect() as conn:
        migrate(conn)
        result = refresh(conn)
    print(f"dbt: {'OK' if result.ok else 'FAILED'}, {result.passed} steps passed")
    for failure in result.failed:
        print(f"  FAILED {failure}")
    if result.error:
        print(f"  {result.error}")
    if result.ok and args.command == "docs":
        run_dbt(("docs", "generate", "--static"))
        print(f"lineage docs: {DBT_DIR / 'target' / 'static_index.html'}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
