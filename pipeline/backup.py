"""Back up the database to S3 in FL's personal AWS account (decision #44).

    uv run python -m pipeline.backup run             # back up now (the daily run does this itself)
    uv run python -m pipeline.backup restore-check   # restore the newest backup into a scratch
                                                     #   database and compare its row counts

Every table except the analytics_* schemas, which dbt rebuilds, goes into one compressed pg_dump
file: daily/<date>.dump, and the month's first also as monthly/<month>.dump. Before anything is
sent, the AWS account is checked against AWS_BACKUP_ACCOUNT_ID, so a backup can never land in
another account, such as a work account configured on the same computer. The key only lets this
code read and write the bucket, never delete: old backups expire by a lifecycle rule on the bucket.
Off until AWS_PROFILE, S3_BACKUP_BUCKET and AWS_BACKUP_ACCOUNT_ID are all set in .env.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from pipeline.config import load_settings

CONTAINER = "jobhunt-postgres"  # docker-compose.yml container_name
RESTORE_DB = "jobhunt_restore_check"
SHRINK_ALARM = 0.7  # a backup under 70% of the previous one means data may have gone missing
# Row counts stored with each backup, to check a restore against.
COUNTED_TABLES = (
    "raw.job_postings",
    "raw.job_sightings",
    "gate.results",
    "gate.labels",
    "agents.jd_briefs",
    "agents.fit_scores",
    "agents.llm_calls",
    "agents.tailored_resumes",
    "agents.queue_items",
    "agents.application_events",
    "ops.daily_runs",
)


class BackupError(RuntimeError):
    """The backup didn't happen or can't be trusted."""


@dataclass(frozen=True)
class BackupSettings:
    profile: str
    bucket: str
    region: str
    account_id: str

    @property
    def enabled(self) -> bool:
        return bool(self.profile and self.bucket and self.account_id)


def backup_settings() -> BackupSettings:
    load_settings()  # loads .env
    return BackupSettings(
        profile=os.environ.get("AWS_PROFILE", "").strip(),
        bucket=os.environ.get("S3_BACKUP_BUCKET", "").strip(),
        region=os.environ.get("AWS_REGION", "us-west-2").strip() or "us-west-2",
        account_id=os.environ.get("AWS_BACKUP_ACCOUNT_ID", "").strip(),
    )


class S3(Protocol):
    def put_object(self, **kwargs: Any) -> Any: ...
    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]: ...
    def download_file(self, bucket: str, key: str, filename: str) -> None: ...


def connect_s3(settings: BackupSettings) -> S3:
    """An S3 client for the backup profile, after checking it is the expected account."""
    import boto3

    session = boto3.Session(profile_name=settings.profile, region_name=settings.region)
    account = session.client("sts").get_caller_identity()["Account"]
    if account != settings.account_id:
        raise BackupError(
            f"AWS profile {settings.profile!r} belongs to another account than "
            "AWS_BACKUP_ACCOUNT_ID; nothing was sent"
        )
    return session.client("s3")


# ---------------------------------------------------------------- the database side


def docker_exe() -> str:
    found = shutil.which("docker")
    if found:
        return found
    path = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "DockerDesktop"
        / "resources"
        / "bin"
        / "docker.exe"
    )
    return str(path)


def _container_command(*args: str) -> list[str]:
    """pg_dump or pg_restore: inside the Postgres container through Docker on the laptop, or,
    when PG_TOOLS_DIR is set (the Airflow container, decision #46), the matching client tools
    there, reaching the server over the network."""
    settings = load_settings()
    tools = os.environ.get("PG_TOOLS_DIR")
    if tools:
        host = ["-h", settings.postgres_host, "-p", str(settings.postgres_port)]
        tool = f"{tools.rstrip('/')}/{args[0]}"  # a Linux path, also when tests run on Windows
        return [tool, *host, "-U", settings.postgres_user, *args[1:]]
    user = settings.postgres_user
    return [docker_exe(), "exec", "-i", CONTAINER, *args[:1], "-U", user, *args[1:]]


def _tool_env() -> dict[str, str] | None:
    """The password for the client tools, passed in their environment, never on the command line.
    Through Docker the container's own login is used, so nothing is added there."""
    if not os.environ.get("PG_TOOLS_DIR"):
        return None
    return {**os.environ, "PGPASSWORD": load_settings().postgres_password}


def dump_database(target: Path, database: str | None = None) -> None:
    """pg_dump in the container, compressed, without the rebuildable analytics schemas."""
    database = database or load_settings().postgres_db
    with target.open("wb") as handle:
        done = subprocess.run(  # noqa: S603 - fixed program, no shell
            _container_command(
                "pg_dump", "-d", database, "-Fc", "-Z", "6", "--exclude-schema=analytics_*"
            ),
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
            env=_tool_env(),
        )
    if done.returncode != 0:
        raise BackupError(f"pg_dump failed: {done.stderr.decode(errors='replace')[-300:]}")


def row_counts(conn: Any, tables: tuple[str, ...] = COUNTED_TABLES) -> dict[str, int]:
    return {
        table: conn.execute(f"select count(*) from {table}").fetchone()[0]  # noqa: S608
        for table in tables
    }


def restore_check(dump: Path, expected: dict[str, int]) -> list[str]:
    """Restore a dump into a scratch database, compare row counts, drop it. [] means it matches."""
    from psycopg import sql

    from pipeline.db import connect

    settings = load_settings()
    admin = connect(settings)
    admin.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(RESTORE_DB)))
    admin.execute(sql.SQL("create database {}").format(sql.Identifier(RESTORE_DB)))
    try:
        with dump.open("rb") as handle:
            done = subprocess.run(  # noqa: S603 - fixed program, no shell
                _container_command("pg_restore", "-d", RESTORE_DB, "--no-owner"),
                stdin=handle,
                capture_output=True,
                check=False,
                env=_tool_env(),
            )
        if done.returncode != 0:
            return [f"pg_restore failed: {done.stderr.decode(errors='replace')[-300:]}"]
        from dataclasses import replace

        with connect(replace(settings, postgres_db=RESTORE_DB)) as restored:
            got = row_counts(restored, tuple(expected))
        return [
            f"{table}: {got[table]} rows restored, {count} expected"
            for table, count in expected.items()
            if got[table] != count
        ]
    finally:
        admin.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(RESTORE_DB)))
        admin.close()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- the S3 side


@dataclass
class BackupResult:
    key: str
    size_bytes: int
    monthly_key: str | None = None
    warnings: list[str] = field(default_factory=list)
    restore_problems: list[str] | None = None  # None = not checked this time

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "size_mb": round(self.size_bytes / 1_000_000, 1),
            "monthly_key": self.monthly_key,
            "warnings": self.warnings,
            "restore_problems": self.restore_problems,
        }


def _keys(s3: S3, bucket: str, prefix: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    token = None
    while True:
        kwargs = {
            "Bucket": bucket,
            "Prefix": prefix,
            **({"ContinuationToken": token} if token else {}),
        }
        page = s3.list_objects_v2(**kwargs)
        objects += page.get("Contents", [])
        if not page.get("IsTruncated"):
            return objects
        token = page["NextContinuationToken"]


def _upload(s3: S3, bucket: str, key: str, path: Path, sha: str, counts: dict[str, int]) -> None:
    with path.open("rb") as body:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ServerSideEncryption="AES256",
            Metadata={"sha256": sha, "row-counts": json.dumps(counts, separators=(",", ":"))},
        )
    head = s3.head_object(Bucket=bucket, Key=key)
    if head["ContentLength"] != path.stat().st_size or head["Metadata"].get("sha256") != sha:
        raise BackupError(f"{key} in S3 doesn't match the file that was sent")


def upload_backup(
    s3: S3,
    bucket: str,
    dump: Path,
    counts: dict[str, int],
    today: date,
    restore: Any = restore_check,
) -> BackupResult:
    """Send one dump: today's daily copy, and the month's first as a monthly copy, which is also
    restored and checked. A much smaller dump than the last one is reported."""
    size, sha = dump.stat().st_size, sha256_of(dump)
    previous = sorted(_keys(s3, bucket, "daily/"), key=lambda o: o["Key"])
    result = BackupResult(key=f"daily/{today.isoformat()}.dump", size_bytes=size)
    earlier = [o for o in previous if o["Key"] < result.key]
    if earlier and size < SHRINK_ALARM * earlier[-1]["Size"]:
        result.warnings.append(
            f"this backup is {size / earlier[-1]['Size']:.0%} the size of the last one "
            f"({earlier[-1]['Key']}): check that no data went missing"
        )
    _upload(s3, bucket, result.key, dump, sha, counts)
    monthly = f"monthly/{today:%Y-%m}.dump"
    if not _keys(s3, bucket, monthly):
        _upload(s3, bucket, monthly, dump, sha, counts)
        result.monthly_key = monthly
        result.restore_problems = restore(dump, counts)
    return result


def run_backup(conn: Any, today: date, settings: BackupSettings | None = None) -> BackupResult:
    settings = settings or backup_settings()
    s3 = connect_s3(settings)
    with tempfile.TemporaryDirectory() as folder:
        dump = Path(folder) / "jobhunt.dump"
        counts = row_counts(conn)
        dump_database(dump)
        return upload_backup(s3, settings.bucket, dump, counts, today)


def check_latest(settings: BackupSettings | None = None) -> tuple[str, list[str]]:
    """Download the newest daily backup, restore it and compare with the counts stored with it."""
    settings = settings or backup_settings()
    s3 = connect_s3(settings)
    newest = max(_keys(s3, settings.bucket, "daily/"), key=lambda o: o["Key"], default=None)
    if newest is None:
        raise BackupError("no backups in the bucket yet")
    key = newest["Key"]
    counts = json.loads(s3.head_object(Bucket=settings.bucket, Key=key)["Metadata"]["row-counts"])
    with tempfile.TemporaryDirectory() as folder:
        dump = Path(folder) / "jobhunt.dump"
        s3.download_file(settings.bucket, key, str(dump))
        return key, restore_check(dump, counts)


def main(argv: list[str] | None = None) -> int:
    from pipeline.daily import report_timezone
    from pipeline.db import connect

    parser = argparse.ArgumentParser(prog="python -m pipeline.backup")
    parser.add_argument("command", choices=("run", "restore-check"))
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    settings = backup_settings()
    if not settings.enabled:
        print("backup is off: set AWS_PROFILE, S3_BACKUP_BUCKET and AWS_BACKUP_ACCOUNT_ID in .env")
        return 1
    try:
        if args.command == "run":
            from datetime import datetime

            with connect() as conn:
                result = run_backup(conn, datetime.now(report_timezone()).date(), settings)
            print(json.dumps(result.as_dict(), indent=1))
            return 0 if not result.warnings and not result.restore_problems else 1
        key, problems = check_latest(settings)
    except BackupError as exc:
        print(f"FAILED {exc}")
        return 1
    print(f"{key}: " + ("restored, every table matches" if not problems else "; ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
