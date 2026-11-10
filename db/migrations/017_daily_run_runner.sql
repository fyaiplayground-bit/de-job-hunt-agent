-- Which scheduler ran each daily run (decision #46): the Windows scheduled task, or the Airflow
-- DAG while it runs beside it. Every run before this migration came from the Windows task.
alter table ops.daily_runs
    add column runner text not null default 'windows'
        check (runner in ('windows', 'airflow'));
