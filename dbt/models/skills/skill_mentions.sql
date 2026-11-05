-- One row per skill named in a requirement: "Python or Java" gives two rows, so the market's demand
-- for each is counted. Wordings of one skill share a key through the vocabulary ("Data pipelines"
-- and "ETL pipelines" are both ETL).
--
-- status says where the profile stands on this skill by its own name, from every wording fit
-- scoring would accept: have, learning or not_covered. It is about the skill, not the requirement:
-- Python covering "Python or Java" says nothing about Java.
with parts as (
    select
        r.*,
        trim(part) as skill_part,
        count(*) over (
            partition by r.posting_version_id, r.kind, r.requirement
        ) as alternatives
    from {{ ref('skill_requirements') }} r,
        lateral regexp_split_to_table(r.requirement, '\s+or\s+', 'i') as part
    where trim(part) <> ''
),

named as (
    select
        p.*,
        coalesce(s.canonical, p.skill_part) as skill_label,
        lower(coalesce(s.canonical, p.skill_part)) as skill_key
    from parts p
    left join {{ ref('skill_synonyms') }} s on s.wording_key = lower(p.skill_part)
),

display as (
    select skill_key, mode() within group (order by skill_label) as skill_name
    from named
    group by skill_key
),

own_status as (
    select distinct on (term_key) term_key, status
    from {{ source('agents', 'profile_skills') }}
    order by term_key, status
)

select
    n.posting_version_id,
    n.kind,
    n.requirement,
    n.weight,
    n.alternatives,
    n.skill_part,
    n.skill_key,
    d.skill_name,
    n.is_covered,
    coalesce(
        direct.status,
        canonical.status,
        'not_covered'
    ) as status
from named n
join display d using (skill_key)
left join own_status direct on direct.term_key = lower(n.skill_part)
left join own_status canonical on canonical.term_key = n.skill_key
