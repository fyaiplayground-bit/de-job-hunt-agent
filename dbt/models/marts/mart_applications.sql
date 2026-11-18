-- One row per job from FL's real profile that reached the queue, with where it stands now
-- (decision #57). The status is the latest event; "silent" is worked out, not recorded: an
-- application still at "applied" after silent_after_days with no news.
with events as (
    select
        posting_version_id,
        status,
        reason,
        created_at,
        row_number() over (partition by posting_version_id order by event_id desc) as newest
    from {{ ref('stg_application_events') }}
),

applied as (
    select posting_version_id, min(created_at) as applied_at
    from {{ ref('stg_application_events') }}
    where status = 'applied'
    group by posting_version_id
)

select
    q.posting_version_id,
    q.batch_date,
    q.batch_number,
    q.company,
    q.title,
    q.score,
    q.site,
    q.work_mode,
    q.location,
    q.url,
    q.review_page,
    a.applied_at,
    (a.applied_at at time zone 'America/Los_Angeles')::date as applied_on,
    e.status,
    e.reason,
    e.created_at as status_at,
    {{ as_of() }} - (e.created_at at time zone 'America/Los_Angeles')::date as days_in_status,
    e.status = 'applied'
        and {{ as_of() }} - (a.applied_at at time zone 'America/Los_Angeles')::date
            >= {{ var('silent_after_days') }} as silent
from {{ ref('stg_queue_items') }} q
join events e on e.posting_version_id = q.posting_version_id and e.newest = 1
left join applied a on a.posting_version_id = q.posting_version_id
where not q.sample
