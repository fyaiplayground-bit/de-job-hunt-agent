"""The S3 backup (decision #44). A fake S3 stands in for AWS, so nothing here costs money or needs a
key. The restore check runs for real against the throwaway test database."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import backup as backup_module
from pipeline.backup import (
    BackupError,
    BackupSettings,
    connect_s3,
    dump_database,
    restore_check,
    row_counts,
    upload_backup,
)
from pipeline.daily import DailySummary, backup_database, render_report

NOV_6 = date(2026, 11, 6)
COUNTS = {"raw.job_postings": 3}


class FakeS3:
    """A bucket in a dict. Like the real key, it can't delete."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.corrupt_next = False

    def put_object(self, Bucket, Key, Body, ServerSideEncryption, Metadata):
        assert ServerSideEncryption == "AES256"
        data = Body.read()
        if self.corrupt_next:
            data, self.corrupt_next = data[:-1], False
        self.objects[Key] = {"data": data, "Metadata": Metadata}

    def head_object(self, Bucket, Key):
        item = self.objects[Key]
        return {"ContentLength": len(item["data"]), "Metadata": item["Metadata"]}

    def list_objects_v2(self, Bucket, Prefix, **kwargs):
        contents = [
            {"Key": key, "Size": len(item["data"])}
            for key, item in sorted(self.objects.items())
            if key.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[key]["data"])


def dump_file(tmp_path, size=1000):
    path = tmp_path / "x.dump"
    path.write_bytes(b"d" * size)
    return path


def no_restore(dump, counts):
    return []


def test_first_backup_of_the_month_is_also_kept_monthly_and_restore_checked(tmp_path):
    s3, checked = FakeS3(), []
    result = upload_backup(
        s3,
        "b",
        dump_file(tmp_path),
        COUNTS,
        NOV_6,
        restore=lambda dump, counts: checked.append(counts) or [],
    )
    assert result.key == "daily/2026-11-06.dump"
    assert result.monthly_key == "monthly/2026-11.dump"
    assert set(s3.objects) == {"daily/2026-11-06.dump", "monthly/2026-11.dump"}
    assert checked == [COUNTS]
    assert result.restore_problems == []
    stored = s3.objects["daily/2026-11-06.dump"]["Metadata"]
    assert json.loads(stored["row-counts"]) == COUNTS
    assert len(stored["sha256"]) == 64


def test_later_days_are_daily_only(tmp_path):
    s3 = FakeS3()
    upload_backup(s3, "b", dump_file(tmp_path), COUNTS, NOV_6, restore=no_restore)
    result = upload_backup(
        s3, "b", dump_file(tmp_path), COUNTS, date(2026, 11, 7), restore=no_restore
    )
    assert result.monthly_key is None
    assert result.restore_problems is None  # not checked on an ordinary day
    assert "daily/2026-11-07.dump" in s3.objects


def test_a_much_smaller_backup_is_reported(tmp_path):
    s3 = FakeS3()
    upload_backup(s3, "b", dump_file(tmp_path, 1000), COUNTS, NOV_6, restore=no_restore)
    result = upload_backup(
        s3, "b", dump_file(tmp_path, 500), COUNTS, date(2026, 11, 7), restore=no_restore
    )
    assert "50% the size of the last one" in result.warnings[0]


def test_a_file_that_arrives_wrong_is_an_error(tmp_path):
    s3 = FakeS3()
    s3.corrupt_next = True
    with pytest.raises(BackupError, match="doesn't match"):
        upload_backup(s3, "b", dump_file(tmp_path), COUNTS, NOV_6, restore=no_restore)


def test_the_wrong_account_is_refused_before_anything_is_sent(monkeypatch):
    sent = []

    class Session:
        def __init__(self, profile_name, region_name):
            pass

        def client(self, name):
            if name == "sts":
                return SimpleNamespace(get_caller_identity=lambda: {"Account": "999999999999"})
            sent.append(name)
            return FakeS3()

    import boto3

    monkeypatch.setattr(boto3, "Session", Session)
    settings = BackupSettings("p", "b", "us-west-2", "111111111111")
    with pytest.raises(BackupError, match="another account"):
        connect_s3(settings)
    assert sent == []  # no S3 client was even made


@pytest.mark.parametrize(
    "values, enabled",
    [
        (("p", "b", "us-west-2", "1"), True),
        (("", "b", "us-west-2", "1"), False),
        (("p", "", "us-west-2", "1"), False),
        (("p", "b", "us-west-2", ""), False),  # no account to check against: never send
    ],
)
def test_backup_is_off_until_everything_is_set(values, enabled):
    assert BackupSettings(*values).enabled is enabled


def test_daily_run_skips_backup_when_it_is_not_set_up(monkeypatch):
    monkeypatch.setattr(
        backup_module, "backup_settings", lambda: BackupSettings("", "", "us-west-2", "")
    )
    summary = DailySummary(local_date="2026-11-06", window_days=2)
    backup_database(None, summary, NOV_6)
    assert summary.backup_status == "off"
    assert "## 备份" not in render_report(summary)


def test_a_failed_backup_is_reported_and_the_day_goes_on(monkeypatch):
    monkeypatch.setattr(
        backup_module, "backup_settings", lambda: BackupSettings("p", "b", "us-west-2", "1")
    )

    def fails(conn, today, settings):
        raise BackupError("no network")

    monkeypatch.setattr(backup_module, "run_backup", fails)
    summary = DailySummary(local_date="2026-11-06", window_days=2)
    backup_database(None, summary, NOV_6)
    assert summary.backup_status == "error"
    assert "备份失败" in render_report(summary)


def test_report_shows_the_backup_and_the_restore_check():
    summary = DailySummary(
        local_date="2026-11-06",
        window_days=2,
        backup_status="ok",
        backup={
            "key": "daily/2026-11-06.dump",
            "size_mb": 73.4,
            "monthly_key": "monthly/2026-11.dump",
            "warnings": [],
            "restore_problems": [],
        },
    )
    text = render_report(summary)
    assert "`daily/2026-11-06.dump`（73.4 MB）" in text
    assert "恢复成功" in text


@pytest.mark.db
def test_a_real_dump_restores_with_every_row(db, greenhouse_jobs, tmp_path):
    from datetime import UTC, datetime
    from uuid import uuid4

    from pipeline.load import load_jobs

    run_id = uuid4()
    db.execute(
        "insert into raw.ingest_runs (run_id, source, target, started_at, status)"
        " values (%s, 'greenhouse', 'example', now(), 'running')",
        (run_id,),
    )
    load_jobs(db, "greenhouse", "example", greenhouse_jobs, run_id, datetime.now(UTC))
    counts = row_counts(db, ("raw.job_postings", "raw.job_sightings"))
    assert counts["raw.job_postings"] > 0
    dump = tmp_path / "test.dump"
    dump_database(dump, "jobhunt_test")
    assert dump.stat().st_size > 0
    assert restore_check(dump, counts) == []
    wrong = {**counts, "raw.job_postings": counts["raw.job_postings"] + 1}
    assert restore_check(dump, wrong) == [
        f"raw.job_postings: {counts['raw.job_postings']} rows restored, "
        f"{wrong['raw.job_postings']} expected"
    ]


def test_inside_the_airflow_container_the_tools_reach_the_server_over_the_network(monkeypatch):
    """No Docker inside Docker (decision #46): the matching client tools, password in the env."""
    from pipeline import backup

    monkeypatch.setenv("PG_TOOLS_DIR", "/usr/lib/postgresql/17/bin")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    command = backup._container_command("pg_dump", "-d", "jobhunt")
    assert command[:5] == ["/usr/lib/postgresql/17/bin/pg_dump", "-h", "postgres", "-p", "5432"]
    assert command[-2:] == ["-d", "jobhunt"]
    assert not any("password" in part.lower() for part in command)
    assert backup._tool_env()["PGPASSWORD"]


def test_on_the_laptop_the_tools_run_in_the_postgres_container(monkeypatch):
    from pipeline import backup

    monkeypatch.delenv("PG_TOOLS_DIR", raising=False)
    command = backup._container_command("pg_dump", "-d", "jobhunt")
    assert command[1:4] == ["exec", "-i", backup.CONTAINER]
    assert backup._tool_env() is None
