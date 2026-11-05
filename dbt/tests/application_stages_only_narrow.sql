-- Nobody is approved without being queued, or applied without being approved.
with stages as (
    select stage_order, jobs_real, jobs_sample from {{ ref('mart_funnel') }}
    where stage in ('Queued', 'Approved', 'Applied')
)

select later.stage_order
from stages later
join stages earlier on earlier.stage_order = later.stage_order - 1
where later.jobs_real > earlier.jobs_real or later.jobs_sample > earlier.jobs_sample
