"""Database connection and schema migrations.

Migrations are numbered SQL files in db/migrations/. Each runs once, inside a transaction, and
is recorded in public.schema_migrations, so `migrate()` is safe to call on every run.
"""

from pathlib import Path

import psycopg

from pipeline.config import Settings, load_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def connect(settings: Settings | None = None) -> psycopg.Connection:
    """Open an autocommit connection; callers group writes with `conn.transaction()`."""
    settings = settings or load_settings()
    return psycopg.connect(settings.postgres_conninfo(), autocommit=True, connect_timeout=5)


def migrate(conn: psycopg.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply migrations that haven't run yet, in filename order. Returns the ones applied."""
    conn.execute(
        "create table if not exists public.schema_migrations ("
        " filename text primary key, applied_at timestamptz not null default now())"
    )
    applied = {row[0] for row in conn.execute("select filename from public.schema_migrations")}
    newly_applied = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "insert into public.schema_migrations (filename) values (%s)", (path.name,)
            )
        newly_applied.append(path.name)
    return newly_applied
