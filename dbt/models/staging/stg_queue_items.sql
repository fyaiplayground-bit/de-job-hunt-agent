select
    posting_version_id,
    batch_date,
    batch_number,
    sample,
    snapshot->>'company' as company,
    snapshot->>'title' as title,
    snapshot->>'site' as site,
    (snapshot->>'score')::int as score,
    (snapshot->>'cost_usd')::numeric as resume_cost_usd,
    created_at
from {{ source('agents', 'queue_items') }}
