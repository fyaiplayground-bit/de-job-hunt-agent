-- Cross-source dedupe (decision #24), as views: nothing stored, always current, recomputable.
-- Replaced by dbt staging models in Milestone 3.
--
-- Identity rule v1, exact matches only. A job's identity is (ATS, board, ATS job id):
--   greenhouse / lever, fetched directly      -> 'greenhouse/<board>/<id>'
--   freehire job whose ATS is greenhouse/lever -> the same key, from external_id '<board>:<id>'
--   other freehire jobs                         -> 'freehire:<ats>/<external_id>'
--   anything else (linkedin)                    -> '<source>/<company>/<id>' (no cross-source match
--                                                  yet; fuzzy matching gets its own versioned rules)

create schema if not exists dedupe;

create view dedupe.job_identity as
select
    p.posting_version_id,
    p.source,
    p.company,
    p.source_job_id,
    case
        when p.source in ('greenhouse', 'lever')
            then p.source || '/' || lower(p.company) || '/' || p.source_job_id
        when p.source = 'freehire'
             and p.payload->>'source' in ('greenhouse', 'lever')
             and p.payload->>'external_id' like '%:%'
            then (p.payload->>'source') || '/'
                 || lower(split_part(p.payload->>'external_id', ':', 1)) || '/'
                 || split_part(p.payload->>'external_id', ':', 2)
        when p.source = 'freehire'
            then 'freehire:' || coalesce(p.payload->>'source', '?') || '/'
                 || coalesce(p.payload->>'external_id', p.source_job_id)
        else p.source || '/' || p.company || '/' || p.source_job_id
    end as identity_key,
    -- Which copy wins when several sources have the same job: the ATS itself, then the
    -- aggregator, then LinkedIn.
    case p.source when 'greenhouse' then 1 when 'lever' then 1 when 'freehire' then 2 else 3 end
        as source_rank
from raw.job_postings p;

-- One row per job: the latest version from the best-ranked source, plus every source that has it.
create view dedupe.jobs as
with ranked as (
    select
        i.*,
        row_number() over (
            partition by i.identity_key
            order by i.source_rank, i.posting_version_id desc
        ) as pick
    from dedupe.job_identity i
)
select
    r.identity_key,
    r.posting_version_id as chosen_posting_version_id,
    r.source as chosen_source,
    (select array_agg(distinct i.source order by i.source)
       from dedupe.job_identity i where i.identity_key = r.identity_key) as sources,
    (select count(distinct (i.source, i.source_job_id))
       from dedupe.job_identity i where i.identity_key = r.identity_key) as copies
from ranked r
where r.pick = 1;
