select
    subscription_id,
    customer_id                 as metronome_customer_id,
    plan,
    cast(start_date as date)    as start_date,
    cast(end_date as date)      as end_date
from {{ source('metronome', 'plan_subscriptions') }}
