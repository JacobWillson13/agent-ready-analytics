select
    i.invoice_id,
    oc.customer_id,
    oc.org_id,
    i.plan,
    i.period_start,
    i.period_end,
    min(i.issued_date)          as issued_date,
    sum(i.amount_usd)           as amount_usd
from {{ ref('stg_metronome__invoice_lines') }} i
join {{ ref('int_org_customers') }} oc using (metronome_customer_id)
where not oc.is_internal
group by 1, 2, 3, 4, 5, 6
