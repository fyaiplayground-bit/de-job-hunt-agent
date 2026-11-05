-- Which skills the market asks for: postings first seen in the last 30 days, compared week on week.
-- Counts each posting once per skill. Only briefed postings count, so every figure comes with how
-- many postings stand behind it.
with jobs as (
    select b.posting_version_id, p.first_seen
    from {{ ref('stg_briefs') }} b
    join {{ ref('stg_postings') }} p using (posting_version_id)
    where p.first_seen > {{ as_of() }} - 30
),

totals as (
    select
        count(*) as jobs_30d,
        count(*) filter (where first_seen > {{ as_of() }} - 7) as jobs_last_7d,
        count(*) filter (
            where first_seen <= {{ as_of() }} - 7 and first_seen > {{ as_of() }} - 14
        ) as jobs_prior_7d
    from jobs
),

counted as (
    select
        m.skill_key,
        min(m.skill_name) as skill_name,
        count(distinct m.posting_version_id) filter (where m.kind = 'must_have') as must_have_jobs,
        count(distinct m.posting_version_id) filter (where m.kind = 'nice_to_have') as nice_jobs,
        count(distinct m.posting_version_id) filter (
            where m.kind = 'must_have' and j.first_seen > {{ as_of() }} - 7
        ) as must_have_last_7d,
        count(distinct m.posting_version_id) filter (
            where m.kind = 'must_have' and j.first_seen <= {{ as_of() }} - 7
            and j.first_seen > {{ as_of() }} - 14
        ) as must_have_prior_7d,
        case
            when bool_or(m.status = 'have') then 'have'
            when bool_or(m.status = 'learning') then 'learning'
            else 'not_covered'
        end as status
    from {{ ref('skill_mentions') }} m
    join jobs j using (posting_version_id)
    group by m.skill_key
)

select
    c.skill_name,
    c.skill_key,
    c.status,
    c.must_have_jobs,
    c.nice_jobs,
    t.jobs_30d,
    round(c.must_have_jobs::numeric / nullif(t.jobs_30d, 0), 3) as must_have_share,
    c.must_have_last_7d,
    c.must_have_prior_7d,
    t.jobs_last_7d,
    t.jobs_prior_7d,
    case
        when t.jobs_last_7d < {{ var('min_trend_jobs') }}
            or t.jobs_prior_7d < {{ var('min_trend_jobs') }} then 'not_enough_data'
        when c.must_have_last_7d::numeric / t.jobs_last_7d
            > c.must_have_prior_7d::numeric / t.jobs_prior_7d + 0.05 then 'up'
        when c.must_have_last_7d::numeric / t.jobs_last_7d
            < c.must_have_prior_7d::numeric / t.jobs_prior_7d - 0.05 then 'down'
        else 'flat'
    end as trend,
    row_number() over (order by c.must_have_jobs desc, c.nice_jobs desc, c.skill_name) as rank
from counted c
cross join totals t
