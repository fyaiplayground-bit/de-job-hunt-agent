"""The daily job hunt as an Airflow DAG (decisions #45, #46).

One task per step of pipeline/daily_steps.py, the same steps the Windows scheduled task runs in
one go. Each task runs one step from the command line in the project's own Python environment
(/opt/jobhunt-venv, built from uv.lock), so Airflow's packages and the pipeline's never mix.

    start → fetch_greenhouse ┐
            fetch_lever      ├→ gate → summarize → analyze → score → analytics → backup → finish
            fetch_freehire   │
            fetch_linkedin   ┘

- Triggered by hand while it runs beside the Windows task (step 4.4); no schedule yet.
- A fetch that fails is retried twice, five minutes apart; the steps save their results, so a
  retry keeps what earlier tries stored.
- A source turned off in .env, the briefing when AI is off, and scoring when there is nothing
  to score show as skipped, not failed.
- finish always runs: it writes the report (output/daily/airflow/) and marks the run, naming any
  step that failed.
"""

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

STEP = "cd /opt/jobhunt && /opt/jobhunt-venv/bin/python -m pipeline.daily_steps"
RUN_ID = "--run-id {{ ti.xcom_pull(task_ids='start') }}"
SOURCES = ("greenhouse", "lever", "freehire", "linkedin")

with DAG(
    dag_id="daily_job_hunt",
    description="Fetch, check, brief and score today's job postings, then rebuild and back up",
    schedule=None,
    start_date=pendulum.datetime(2026, 11, 1, tz="America/Los_Angeles"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0, "execution_timeout": timedelta(minutes=45)},
    tags=["job-hunt"],
    doc_md=__doc__,
):
    start = BashOperator(task_id="start", bash_command=f"{STEP} start --runner airflow")
    fetches = [
        BashOperator(
            task_id=f"fetch_{source}",
            bash_command=f"{STEP} fetch {RUN_ID} --source {source}",
            retries=2,
            retry_delay=timedelta(minutes=5),
        )
        for source in SOURCES
    ]
    gate = BashOperator(
        task_id="gate",
        bash_command=f"{STEP} gate {RUN_ID}",
        # Go on when every fetch either worked or was skipped (a source turned off).
        trigger_rule="none_failed_min_one_success",
    )
    summarize = BashOperator(task_id="summarize", bash_command=f"{STEP} summarize {RUN_ID}")
    analyze = BashOperator(
        task_id="analyze",
        bash_command=f"{STEP} analyze {RUN_ID}",
        execution_timeout=timedelta(minutes=90),
    )
    score = BashOperator(task_id="score", bash_command=f"{STEP} score {RUN_ID}")
    # dbt and the backup run whether or not there was anything to brief or score.
    analytics = BashOperator(
        task_id="analytics", bash_command=f"{STEP} analytics {RUN_ID}", trigger_rule="none_failed"
    )
    backup = BashOperator(
        task_id="backup", bash_command=f"{STEP} backup {RUN_ID}", trigger_rule="none_failed"
    )
    finish = BashOperator(
        task_id="finish", bash_command=f"{STEP} finish {RUN_ID}", trigger_rule="all_done"
    )

    start >> fetches >> gate >> summarize >> analyze >> score >> analytics >> backup >> finish
