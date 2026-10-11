with orgs as (
    select * from {{ ref('dim_orgs') }} where not is_internal
),

metered as (
    select
        m.org_id,
        u.usage_date,
        sum(if(u.billable_metric = 'base_traces', u.quantity, 0))       as base_traces,
        sum(if(u.billable_metric = 'extended_traces', u.quantity, 0))   as extended_traces,
        max(if(u.billable_metric = 'seats', u.quantity, null))          as billed_seats
    from {{ ref('stg_metronome__usage') }} u
    join {{ ref('stg_metronome__customers') }} m using (metronome_customer_id)
    group by 1, 2
),

events as (
    select org_id, event_date as usage_date, count(*) as product_events, count(distinct user_id) as active_users
    from {{ ref('stg_segment__tracks') }}
    group by 1, 2
),

joined as (
    select
        coalesce(m.org_id, e.org_id)            as org_id,
        coalesce(m.usage_date, e.usage_date)    as usage_date,
        coalesce(m.base_traces, 0)              as base_traces,
        coalesce(m.extended_traces, 0)          as extended_traces,
        m.billed_seats,
        coalesce(e.product_events, 0)           as product_events,
        coalesce(e.active_users, 0)             as active_users
    from metered m
    full outer join events e on m.org_id = e.org_id and m.usage_date = e.usage_date
),

plan_on_day as (
    select j.org_id, j.usage_date, array_agg(s.plan order by s.start_date desc limit 1)[offset(0)] as plan
    from joined j
    join {{ ref('stg_metronome__customers') }} mc on j.org_id = mc.org_id
    join {{ ref('stg_metronome__plan_subscriptions') }} s
      on s.metronome_customer_id = mc.metronome_customer_id
     and j.usage_date between s.start_date and coalesce(s.end_date, date '9999-12-31')
    group by 1, 2
)

select
    concat(j.org_id, '|', cast(j.usage_date as string))  as org_day_id,
    j.org_id,
    o.customer_id,
    j.usage_date,
    coalesce(p.plan, 'none')                              as plan_on_day,
    o.deployment_type,
    j.base_traces,
    j.extended_traces,
    j.billed_seats,
    j.product_events,
    j.active_users
from joined j
join orgs o on j.org_id = o.org_id
left join plan_on_day p on j.org_id = p.org_id and j.usage_date = p.usage_date
where j.usage_date <= date('{{ var("as_of_date") }}')
