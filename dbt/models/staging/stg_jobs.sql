-- One row per real job after cross-source dedupe (the pipeline's own dedupe.jobs view).
{{ config(materialized='table') }}

select
    j.identity_key,
    j.chosen_posting_version_id as posting_version_id,
    j.chosen_source as source,
    j.copies,
    p.company_name,
    p.title,
    p.location,
    p.url,
    p.first_seen,
    p.last_seen,
    p.title ~* '{{ var("de_title_pattern") }}' as is_de_title
from {{ source('dedupe', 'jobs') }} j
join {{ ref('stg_postings') }} p on p.posting_version_id = j.chosen_posting_version_id
