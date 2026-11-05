-- What the AI cost, by day and prompt. Cached answers aren't new calls, so they cost nothing here.
select
    local_date,
    prompt_name,
    count(*) as calls,
    round(sum(cost_usd), 3) as cost_usd,
    sum(input_tokens) as input_tokens,
    sum(output_tokens) as output_tokens,
    sum(cache_read_tokens) as cache_read_tokens
from {{ ref('stg_llm_calls') }}
group by local_date, prompt_name
