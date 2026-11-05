-- Which kind of role the profile covers best, last 30 days.
select
    b.archetype,
    count(*) as jobs_scored,
    count(*) filter (where f.must_have_coverage >= {{ var('coverage_bar') }}) as jobs_clearing_bar,
    round(
        (count(*) filter (where f.must_have_coverage >= {{ var('coverage_bar') }}))::numeric
        / count(*), 3
    ) as coverage_share,
    round(avg(f.score), 1) as average_score
from {{ ref('stg_fit_scores') }} f
join {{ ref('stg_briefs') }} b using (posting_version_id)
join {{ ref('stg_postings') }} p using (posting_version_id)
where p.first_seen > {{ as_of() }} - 30
group by b.archetype
