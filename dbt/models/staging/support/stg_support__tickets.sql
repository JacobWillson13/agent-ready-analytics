select
    id                                  as ticket_id,
    org_id,
    sf_account_id                       as account_id,
    priority,
    status,
    category,
    cast(created_at as timestamp)       as created_at,
    cast(solved_at as timestamp)        as solved_at,
    timestamp_diff(cast(solved_at as timestamp), cast(created_at as timestamp), minute) / 60.0 as hours_to_resolution
from {{ source('support', 'tickets') }}
