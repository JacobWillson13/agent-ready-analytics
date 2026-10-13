select user_id, org_id, lower(email) as email, role, cast(created_at as timestamp) as created_at
from {{ source('app', 'users') }}
