-- dedupe.jobs, same columns and same result, computed in one pass (decision #24).
-- The first version (006) looked up every job's sources with a correlated subquery: one inner
-- query per row, so its cost grew with the square of the row count and it stalled at ~7,000
-- postings. Here the sources are aggregated once per identity and joined to the chosen copy.

create or replace view dedupe.jobs as
with identities as (
    select * from dedupe.job_identity
),
per_identity as (
    select
        identity_key,
        array_agg(distinct source order by source) as sources,
        count(distinct (source, source_job_id)) as copies
    from identities
    group by identity_key
),
chosen as (
    -- the latest version from the best-ranked source (ATS itself, then aggregator, then LinkedIn)
    select distinct on (identity_key) identity_key, posting_version_id, source
    from identities
    order by identity_key, source_rank, posting_version_id desc
)
select
    c.identity_key,
    c.posting_version_id as chosen_posting_version_id,
    c.source as chosen_source,
    p.sources,
    p.copies
from chosen c
join per_identity p using (identity_key);
