-- One row per day the pipeline ran: its last run's status and the day's totals.
with runs as (
    select
        local_date,
        count(*) as runs,
        (array_agg(status order by daily_run_id desc))[1] as last_status,
        sum(new_jobs) as new_jobs,
        sum(new_de_jobs) as new_de_jobs,
        sum(jobs_in_scope) as jobs_in_scope,
        sum(jobs_briefed) as jobs_briefed,
        sum(jobs_over_cap) as jobs_over_cap,
        sum(jobs_scored) as jobs_scored,
        (array_agg(failed_sources order by daily_run_id desc))[1] as failed_sources,
        round(extract(epoch from sum(finished_at - started_at)) / 60, 1) as run_minutes
    from {{ ref('stg_daily_runs') }}
    group by local_date
),

costs as (
    select local_date, sum(cost_usd) as ai_cost_usd
    from {{ ref('stg_llm_calls') }}
    group by local_date
)

select r.*, round(coalesce(c.ai_cost_usd, 0), 2) as ai_cost_usd
from runs r
left join costs c using (local_date)
