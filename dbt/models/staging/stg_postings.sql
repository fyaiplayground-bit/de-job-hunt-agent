-- One row per posting version, with the JSON of each source flattened to the same columns, and
-- when the job was first and last seen on its board. Those dates are Los Angeles days of the run
-- that saw it, like the daily report: seen_on is a UTC date, so an evening run counts as tomorrow.
{{ config(materialized='table') }}

with sightings as (
    select
        s.source,
        s.company,
        s.source_job_id,
        min((r.started_at at time zone 'America/Los_Angeles')::date) as first_seen,
        max((r.started_at at time zone 'America/Los_Angeles')::date) as last_seen
    from {{ source('raw', 'job_sightings') }} s
    join {{ source('raw', 'ingest_runs') }} r using (run_id)
    group by 1, 2, 3
)

select
    p.posting_version_id,
    p.source,
    p.company as company_slug,
    p.source_job_id,
    p.fetched_at,
    s.first_seen,
    s.last_seen,
    coalesce(p.payload->>'title', p.payload->>'text', '') as title,
    case
        when p.source = 'greenhouse' then coalesce(p.payload->>'company_name', p.company)
        when jsonb_typeof(p.payload->'company') = 'string' then p.payload->>'company'
        else p.company
    end as company_name,
    case p.source
        when 'greenhouse' then p.payload->'location'->>'name'
        when 'lever' then p.payload->'categories'->>'location'
        else p.payload->>'location'
    end as location,
    case p.source
        when 'greenhouse' then p.payload->>'absolute_url'
        when 'lever' then p.payload->>'hostedUrl'
        else p.payload->>'url'
    end as url
from {{ source('raw', 'job_postings') }} p
left join sightings s using (source, company, source_job_id)
