select
    c.account_id                as customer_id,
    m.month_start,
    m.as_of_date,
    sum(c.arr_usd)              as enterprise_arr_usd,
    count(*)                    as live_contract_count
from {{ ref('int_months') }} m
join {{ ref('int_contracts') }} c
  on c.contract_start_date <= m.as_of_date
 and c.contract_end_date   >= m.as_of_date
group by 1, 2, 3
