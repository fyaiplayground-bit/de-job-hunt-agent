select
    llm_call_id,
    (created_at at time zone 'America/Los_Angeles')::date as local_date,
    prompt_name,
    prompt_version,
    served_model,
    input_tokens,
    output_tokens,
    cache_read_tokens,
    coalesce(cost_usd, 0) as cost_usd
from {{ source('agents', 'llm_calls') }}
