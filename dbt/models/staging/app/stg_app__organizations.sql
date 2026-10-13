select
    org_id,
    sf_account_id                       as account_id,
    org_name,
    lower(deployment_type)              as deployment_type,
    country,
    is_internal,
    cast(created_at as timestamp)       as created_at,
    date(created_at)                    as signup_date
from {{ source('app', 'organizations') }}
