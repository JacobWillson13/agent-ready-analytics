select id as user_id, name as owner_name, lower(email) as owner_email, title
from {{ source('salesforce', 'user') }}
