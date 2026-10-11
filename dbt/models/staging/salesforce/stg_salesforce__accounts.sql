select
    id                                  as account_id,
    name                                as account_name,
    website,
    industry,
    billing_country,
    employee_count,
    case lower(deployment_type__c)
        when 'cloud' then 'cloud'
        when 'hybrid' then 'hybrid'
        when 'self-hosted' then 'self_hosted'
    end                                 as sf_deployment_type,
    account_status__c                   as account_status,
    owner_id,
    cast(created_date as date)          as created_date
from {{ source('salesforce', 'account') }}
where not is_deleted
