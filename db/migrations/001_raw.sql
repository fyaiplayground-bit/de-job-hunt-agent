-- Raw layer: what each source returned, stored as-is and never updated.

create schema if not exists raw;

-- One row per board per run: what was fetched and whether it worked.
create table raw.ingest_runs (
    run_id       uuid primary key,
    source       text not null,
    company      text not null,
    started_at   timestamptz not null,
    finished_at  timestamptz,
    status       text not null check (status in ('running', 'ok', 'error')),
    jobs_seen    integer,
    versions_new integer,
    error        text
);

-- One row per distinct version of a posting. A new row appears only when the posting's
-- content changes (content_hash), so re-running a day adds nothing.
create table raw.job_postings (
    posting_version_id bigserial primary key,
    source             text not null,
    company            text not null,
    source_job_id      text not null,
    content_hash       text not null,
    payload            jsonb not null,  -- the job exactly as the API returned it
    fetched_at         timestamptz not null,
    run_id             uuid not null references raw.ingest_runs (run_id),
    unique (source, company, source_job_id, content_hash)
);

-- One row per posting per day it was seen on the board (UTC date). First/last seen and how
-- long a job stayed open are derived from this later in dbt.
create table raw.job_sightings (
    source        text not null,
    company       text not null,
    source_job_id text not null,
    seen_on       date not null,
    run_id        uuid not null references raw.ingest_runs (run_id),
    primary key (source, company, source_job_id, seen_on)
);
