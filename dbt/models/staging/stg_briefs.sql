-- One row per posting: its newest jd-analysis brief, flattened.
with versioned as (
    select
        *,
        split_part(prompt_version, '@', 2)::int as prompt_number
    from {{ source('agents', 'jd_briefs') }}
)

select distinct on (posting_version_id)
    posting_version_id,
    prompt_version,
    prompt_number,
    model,
    created_at,
    brief->>'company' as company,
    brief->>'title' as title,
    brief->>'archetype' as archetype,
    brief->>'seniority' as seniority,
    (brief->>'years_required')::numeric as years_required,
    brief->>'work_mode' as work_mode,
    brief->>'sponsorship' as sponsorship,
    brief->'must_haves' as must_haves,
    brief->'nice_to_haves' as nice_to_haves
from versioned
where prompt_number >= {{ var('min_brief_version') }}
order by posting_version_id, prompt_number desc, created_at desc
