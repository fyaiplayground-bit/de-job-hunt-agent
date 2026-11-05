select event_id, posting_version_id, status, reason, created_at
from {{ source('agents', 'application_events') }}
