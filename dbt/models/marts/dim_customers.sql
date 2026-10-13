-- One row per billing customer that has ever paid (enterprise account or self-serve org).
with org_c as (
    select * from {{ ref('dim_orgs') }} where not is_internal
),

ent as (
    select account_id, min(contract_start_date) as first_contract_date
    from {{ ref('int_contracts') }}
    group by 1
),

primary_org as (
    select * from org_c where is_primary_org
),

customer_paid as (
    select customer_id,
           min(first_paid_date) as first_paid_date,
           logical_or(first_paid_plan = 'plus') as had_self_serve
    from org_c
    where is_paid_ever
    group by 1
)

select
    cp.customer_id,
    coalesce(a.account_name, po.org_name)               as customer_name,
    if(e.account_id is not null, 'enterprise', 'self_serve') as motion,
    po.region,
    po.country,
    po.deployment_type,
    a.sf_deployment_type,
    a.industry,
    a.employee_count,
    a.account_status,
    w.owner_name,
    cp.first_paid_date,
    e.first_contract_date,
    e.account_id is not null and cp.had_self_serve      as upgraded_from_self_serve
from customer_paid cp
join primary_org po on cp.customer_id = po.customer_id
left join ent e on cp.customer_id = e.account_id
left join {{ ref('stg_salesforce__accounts') }} a on cp.customer_id = a.account_id
left join {{ ref('stg_salesforce__users') }} w on a.owner_id = w.user_id
