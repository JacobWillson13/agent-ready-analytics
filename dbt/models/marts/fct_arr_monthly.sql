with ent as (
    select * from {{ ref('int_enterprise_arr_monthly') }}
),

ss as (
    select * from {{ ref('int_self_serve_arr_monthly') }}
),

joined as (
    select
        coalesce(e.customer_id, s.customer_id)      as customer_id,
        coalesce(e.month_start, s.month_start)      as month_start,
        coalesce(e.as_of_date, s.as_of_date)        as as_of_date,
        coalesce(e.enterprise_arr_usd, 0)           as enterprise_arr_usd,
        coalesce(s.self_serve_arr_usd, 0)           as self_serve_arr_usd
    from ent e
    full outer join ss s
      on e.customer_id = s.customer_id and e.month_start = s.month_start
)

select
    concat(customer_id, '|', format_date('%Y-%m', month_start)) as customer_month_id,
    customer_id,
    month_start,
    as_of_date,
    if(enterprise_arr_usd > 0, 'enterprise', 'self_serve')     as motion,
    enterprise_arr_usd,
    self_serve_arr_usd,
    enterprise_arr_usd + self_serve_arr_usd                    as arr_usd
from joined
where enterprise_arr_usd + self_serve_arr_usd > 0
