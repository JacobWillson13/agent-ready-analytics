-- One row per closed-won opportunity, annualized.
with won as (
    select *
    from {{ ref('stg_salesforce__opportunities') }}
    where is_won and amount_tcv_usd > 0
      and contract_start_date is not null and contract_end_date is not null
)

select
    opportunity_id                              as contract_id,
    account_id,
    opportunity_type,
    close_date,
    contract_start_date,
    contract_end_date,
    amount_tcv_usd,
    date_diff(date_add(contract_end_date, interval 1 day), contract_start_date, month) as term_months,
    safe_divide(amount_tcv_usd * 12,
        date_diff(date_add(contract_end_date, interval 1 day), contract_start_date, month)) as arr_usd
from won
