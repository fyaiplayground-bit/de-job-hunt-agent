-- How many jobs reach each stage. Stages from "Queued" on come from the event log, so a job that
-- moved on still counts in the stages it passed. Fictional-profile batches are counted separately:
-- they can reach "Approved" but never "Applied".
with reached as (
    select
        e.status,
        count(distinct e.posting_version_id) filter (where not q.sample) as jobs_real,
        count(distinct e.posting_version_id) filter (where q.sample) as jobs_sample
    from {{ ref('stg_application_events') }} e
    join {{ ref('stg_queue_items') }} q using (posting_version_id)
    group by e.status
),

stages as (
    select 1 as stage_order, 'DE jobs found' as stage,
           (select count(*) from {{ ref('stg_jobs') }} where is_de_title) as jobs_real,
           0::bigint as jobs_sample
    union all select 2, 'Briefed by AI', (select count(*) from {{ ref('stg_briefs') }}), 0
    union all select 3, 'Scored', (select count(*) from {{ ref('stg_fit_scores') }}), 0
    union all select 4, 'Worth applying',
        (select count(*) from {{ ref('stg_fit_scores') }} where decision <> 'skip'), 0
),

later (stage_order, stage, status) as (
    values
        (5, 'Queued', 'awaiting_approval'),
        (6, 'Approved', 'approved'),
        (7, 'Applied', 'applied'),
        (8, 'Recruiter screen', 'recruiter_screen'),
        (9, 'Tech screen', 'tech_screen'),
        (10, 'Onsite', 'onsite'),
        (11, 'Offer', 'offer')
)

select stage_order, stage, jobs_real, jobs_sample from stages
union all
select l.stage_order, l.stage, coalesce(r.jobs_real, 0), coalesce(r.jobs_sample, 0)
from later l
left join reached r on r.status = l.status
