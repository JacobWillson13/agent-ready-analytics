select
    {{ dbt_utils.generate_surrogate_key(['invoice_id', 'line_item']) }} as invoice_line_id,
    invoice_id,
    customer_id                 as metronome_customer_id,
    plan,
    cast(period_start as date)  as period_start,
    cast(period_end as date)    as period_end,
    line_item,
    quantity,
    unit_price,
    cast(amount_usd as float64) as amount_usd,
    cast(issued_at as date)     as issued_date
from {{ source('metronome', 'invoices') }}
