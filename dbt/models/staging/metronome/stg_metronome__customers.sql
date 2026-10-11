select customer_id as metronome_customer_id, org_id, salesforce_account_id as account_id, name as customer_name
from {{ source('metronome', 'customers') }}
