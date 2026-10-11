-- Self-serve ARR = 12 x the most recent closed monthly Plus invoice, while the Plus subscription is active.
with plus_subs as (
    select s.metronome_customer_id, s.start_date, s.end_date, oc.customer_id
    from {{ ref('stg_metronome__plan_subscriptions') }} s
    join {{ ref('int_org_customers') }} oc using (metronome_customer_id)
    where s.plan = 'plus' and not oc.is_internal
),

invoices as (
    select metronome_customer_id, invoice_id, period_end, sum(amount_usd) as invoice_total_usd
    from {{ ref('stg_metronome__invoice_lines') }}
    where plan = 'plus'
    group by 1, 2, 3
)

select
    s.customer_id,
    m.month_start,
    m.as_of_date,
    12 * array_agg(i.invoice_total_usd order by i.period_end desc limit 1)[offset(0)] as self_serve_arr_usd
from {{ ref('int_months') }} m
join plus_subs s
  on s.start_date <= m.as_of_date
 and coalesce(s.end_date, date '9999-12-31') >= m.as_of_date
join invoices i
  on i.metronome_customer_id = s.metronome_customer_id
 and i.period_end <= m.as_of_date
group by 1, 2, 3
