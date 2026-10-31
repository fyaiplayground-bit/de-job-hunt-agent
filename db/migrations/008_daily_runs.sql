-- One row per daily run (decision #27): when it ran, how far back searches looked, what it
-- found, where the report is. The next run reads it to size its search window, and Claude reads
-- it at the start of a session to say whether the last run worked.

create schema if not exists ops;

create table ops.daily_runs (
    daily_run_id bigserial primary key,
    started_at   timestamptz not null,
    finished_at  timestamptz,
    local_date   date not null,          -- the day in REPORT_TIMEZONE (America/Los_Angeles)
    status       text not null check (status in ('running', 'ok', 'partial', 'error')),
    window_days  integer,                -- searches looked back this many days
    summary      jsonb,
    report_path  text,
    error        text
);
