"""The Airflow DAG (dags/daily_job_hunt.py) without Airflow installed: every command it runs is
one the step command line accepts, in the order the steps must run (decision #46). The DAG
itself is loaded and checked inside the Airflow container (docs/NOTES.md, "Airflow")."""

import re
from pathlib import Path

from pipeline import daily_steps as steps

DAG_FILE = Path(__file__).resolve().parent.parent / "dags" / "daily_job_hunt.py"
TEXT = DAG_FILE.read_text(encoding="utf-8")


def test_every_step_runs_once_in_order():
    used = re.findall(r"\{STEP\} (\w+)", TEXT)
    assert used == ["start", "fetch", *steps.STEP_ORDER[1:], "finish"]


def test_every_command_parses():
    sources = re.search(r"SOURCES = \(([^)]*)\)", TEXT).group(1)
    for source in re.findall(r'"(\w+)"', sources):
        args = steps.parse_args(["fetch", "--run-id", "1", "--source", source])
        assert args.source == source
    for step in steps.STEP_ORDER[1:]:
        assert steps.parse_args([step, "--run-id", "1"]).step == step
    assert steps.parse_args(["start", "--runner", "airflow"]).runner == "airflow"


def test_every_source_has_a_fetch_task():
    from ingestion.sources import SOURCES

    listed = re.findall(r'"(\w+)"', re.search(r"SOURCES = \(([^)]*)\)", TEXT).group(1))
    assert sorted(listed) == sorted(SOURCES)
