-- Fails if any customer-month ARR differs from the generator's answer key by more than $1.
-- Proves the modeling is right independently of the agent.
with truth as (
    select customer_id, cast(month_start as date) as month_start, sum(arr_usd) as arr_usd
    from {{ source('eval_truth', 'truth_arr_monthly') }}
    group by 1, 2
),
model as (
    select customer_id, month_start, arr_usd from {{ ref('fct_arr_monthly') }}
)
select coalesce(t.customer_id, m.customer_id) as customer_id,
       coalesce(t.month_start, m.month_start) as month_start,
       t.arr_usd as truth_arr, m.arr_usd as model_arr
from truth t
full outer join model m on t.customer_id = m.customer_id and t.month_start = m.month_start
where abs(coalesce(t.arr_usd, 0) - coalesce(m.arr_usd, 0)) > 1
