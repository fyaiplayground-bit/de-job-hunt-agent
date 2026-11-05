-- One row per requirement in a brief, with whether the profile covers it. An either/or entry such
-- as "Python or Java" is one requirement here.
with listed as (
    select b.posting_version_id, 'must_have' as kind, m->>'skill' as requirement,
           m->>'weight' as weight
    from {{ ref('stg_briefs') }} b, jsonb_array_elements(b.must_haves) m
    union all
    select b.posting_version_id, 'nice_to_have', m->>'skill', null
    from {{ ref('stg_briefs') }} b, jsonb_array_elements(b.nice_to_haves) m
),

distinct_listed as (
    select distinct on (posting_version_id, kind, requirement) *
    from listed
    order by posting_version_id, kind, requirement, weight
)

select
    l.posting_version_id,
    l.kind,
    l.requirement,
    l.weight,
    m.requirement is not null as is_covered,
    m.profile_skill,
    m.level,
    m.via
from distinct_listed l
left join {{ ref('stg_fit_matches') }} m
    on m.posting_version_id = l.posting_version_id
    and m.kind = l.kind
    and m.requirement = l.requirement
