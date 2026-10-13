with orgs as (
    select * from {{ ref('int_org_customers') }}
),

traces as (
    select m.org_id, u.usage_date, sum(u.quantity) as base_traces
    from {{ ref('stg_metronome__usage') }} u
    join {{ ref('stg_metronome__customers') }} m using (metronome_customer_id)
    where u.billable_metric = 'base_traces'
    group by 1, 2
),

activation as (
    -- activated = first day cumulative base traces reach 1,000
    select org_id, min(usage_date) as activated_date
    from (
        select org_id, usage_date,
               sum(base_traces) over (partition by org_id order by usage_date) as cum_traces
        from traces
    )
    where cum_traces >= 1000
    group by 1
),

subs as (
    select * from {{ ref('stg_metronome__plan_subscriptions') }}
),

paid as (
    select metronome_customer_id, min(start_date) as first_paid_date,
           array_agg(plan order by start_date limit 1)[offset(0)] as first_paid_plan
    from subs
    where plan in ('plus', 'enterprise')
    group by 1
),

current_plan as (
    select metronome_customer_id, array_agg(plan order by start_date desc limit 1)[offset(0)] as current_plan
    from subs
    where start_date <= date('{{ var("as_of_date") }}')
      and coalesce(end_date, date '9999-12-31') >= date('{{ var("as_of_date") }}')
    group by 1
)

select
    o.org_id,
    o.customer_id,
    o.account_id,
    o.org_name,
    o.deployment_type,
    o.country,
    o.region,
    o.is_internal,
    o.is_primary_org,
    coalesce(cp.current_plan, 'churned')            as current_plan,
    o.signup_date,
    a.activated_date,
    p.first_paid_date,
    p.first_paid_plan,
    date_diff(a.activated_date, o.signup_date, day) as days_to_activate,
    date_diff(p.first_paid_date, o.signup_date, day) as days_to_paid,
    a.activated_date is not null                    as is_activated,
    p.first_paid_date is not null                   as is_paid_ever
from orgs o
left join activation a  on o.org_id = a.org_id
left join paid p        on o.metronome_customer_id = p.metronome_customer_id
left join current_plan cp on o.metronome_customer_id = cp.metronome_customer_id
