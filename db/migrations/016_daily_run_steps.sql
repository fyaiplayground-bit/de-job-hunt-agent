-- The daily run as separate steps (decision #45). Each step saves what it found here, so the next
-- step can start in another process (an Airflow task) and the day's summary can be put together
-- from the saved steps. A retried step replaces its own row.

create table ops.daily_run_steps (
    daily_run_id bigint not null references ops.daily_runs (daily_run_id),
    step         text not null,      -- fetch:<source>, gate, summarize, analyze, score, analytics, backup
    status       text not null check (status in ('ok', 'error')),
    fields       jsonb not null,     -- this step's part of the day's summary
    state        jsonb not null,     -- what later steps need, e.g. ingest run ids, new job ids
    error        text,
    started_at   timestamptz not null,
    finished_at  timestamptz not null,
    primary key (daily_run_id, step)
);
