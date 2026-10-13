select
    cast(usage_id as string)    as usage_id,
    customer_id                 as metronome_customer_id,
    billable_metric_name        as billable_metric,
    cast(usage_date as date)    as usage_date,
    quantity
from {{ source('metronome', 'usage') }}
