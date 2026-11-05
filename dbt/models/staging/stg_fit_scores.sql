-- One row per posting: the newest score of its newest brief. dbt reads the scores Python made and
-- never recomputes them, so the scoring rules live in one place only (decision #41).
select distinct on (f.posting_version_id)
    f.posting_version_id,
    f.brief_prompt_version,
    f.profile_fingerprint,
    f.rules_version,
    f.vocabulary_version,
    f.score,
    f.decision,
    (f.result->>'must_have_coverage')::numeric as must_have_coverage,
    (f.result->>'nice_coverage')::numeric as nice_coverage,
    jsonb_array_length(f.result->'dealbreakers') > 0 as has_dealbreaker,
    split_part(f.result->'dealbreakers'->>0, ':', 1) as dealbreaker,
    f.result,
    f.created_at
from {{ source('agents', 'fit_scores') }} f
join {{ ref('stg_briefs') }} b
    on b.posting_version_id = f.posting_version_id and b.prompt_version = f.brief_prompt_version
order by f.posting_version_id, f.created_at desc, f.rules_version desc, f.vocabulary_version desc
