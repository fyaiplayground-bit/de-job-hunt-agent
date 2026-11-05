-- One row per requirement the score marked covered, and the profile skill that covered it.
select f.posting_version_id, 'must_have' as kind, m->>'asked' as requirement,
       m->>'skill' as profile_skill, m->>'level' as level, m->>'via' as via
from {{ ref('stg_fit_scores') }} f, jsonb_array_elements(f.result->'covered') m
union all
select f.posting_version_id, 'nice_to_have', m->>'asked', m->>'skill', m->>'level', m->>'via'
from {{ ref('stg_fit_scores') }} f, jsonb_array_elements(f.result->'nice_covered') m
