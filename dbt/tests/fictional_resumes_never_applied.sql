-- The lock in agents/application_queue.py, checked again from the data side (decision #40).
select stage from {{ ref('mart_funnel') }}
where stage_order >= 7 and jobs_sample > 0
