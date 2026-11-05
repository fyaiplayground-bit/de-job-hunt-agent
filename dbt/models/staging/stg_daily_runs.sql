select
    daily_run_id,
    local_date,
    status,
    started_at,
    finished_at,
    coalesce((summary->>'new_jobs')::int, 0) as new_jobs,
    coalesce((summary->>'new_de_jobs')::int, 0) as new_de_jobs,
    coalesce((summary->>'jd_in_scope')::int, 0) as jobs_in_scope,
    coalesce((summary->>'jd_analyzed')::int, 0) as jobs_briefed,
    coalesce((summary->>'jd_skipped_by_limit')::int, 0) as jobs_over_cap,
    coalesce((summary->>'jd_cost_usd')::numeric, 0) as brief_cost_usd,
    coalesce((summary->>'fit_scored')::int, 0) as jobs_scored,
    coalesce((
        select count(*) from jsonb_array_elements(summary->'targets') t
        where t->>'status' = 'error'
    ), 0) as failed_sources
from {{ source('ops', 'daily_runs') }}
