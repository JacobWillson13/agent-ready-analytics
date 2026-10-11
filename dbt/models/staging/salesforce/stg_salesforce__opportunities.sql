select
    id                                  as opportunity_id,
    account_id,
    name                                as opportunity_name,
    type                                as opportunity_type,
    stage_name,
    is_closed,
    is_won,
    cast(amount as float64)             as amount_tcv_usd,
    cast(contract_start_date__c as date) as contract_start_date,
    cast(contract_end_date__c as date)  as contract_end_date,
    cast(close_date as date)            as close_date,
    cast(created_date as date)          as created_date
from {{ source('salesforce', 'opportunity') }}
where not is_deleted
