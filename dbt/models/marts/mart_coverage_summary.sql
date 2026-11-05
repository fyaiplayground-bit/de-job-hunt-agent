-- The coverage score: of scored postings first seen in each period, the share where the profile's
-- skills (have + learning, decision #13) clear the apply bar. A dealbreaker doesn't change this:
-- it answers "do my skills cover the job", not "should I apply".
with scored as (
    select
        f.posting_version_id,
        f.must_have_coverage,
        f.decision,
        f.has_dealbreaker,
        f.brief_prompt_version,
        p.first_seen,
        f.must_have_coverage >= {{ var('coverage_bar') }} as clears_bar
    from {{ ref('stg_fit_scores') }} f
    join {{ ref('stg_postings') }} p using (posting_version_id)
),

periods as (
    select 'today' as period, 1 as period_order, {{ as_of() }} as from_date, {{ as_of() }} as to_date
    union all select 'last_7_days', 2, {{ as_of() }} - 6, {{ as_of() }}
    union all select 'prior_7_days', 3, {{ as_of() }} - 13, {{ as_of() }} - 7
    union all select 'last_30_days', 4, {{ as_of() }} - 29, {{ as_of() }}
)

select
    p.period,
    p.period_order,
    count(s.posting_version_id) as jobs_scored,
    count(*) filter (where s.clears_bar) as jobs_clearing_bar,
    round(
        (count(*) filter (where s.clears_bar))::numeric
        / nullif(count(s.posting_version_id), 0), 3
    ) as coverage_share,
    count(*) filter (where s.decision <> 'skip') as jobs_worth_applying,
    count(*) filter (where s.has_dealbreaker) as jobs_with_dealbreaker,
    string_agg(distinct s.brief_prompt_version, ', ') as brief_versions
from periods p
left join scored s on s.first_seen between p.from_date and p.to_date
group by p.period, p.period_order
