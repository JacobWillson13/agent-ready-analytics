# Customer 360 in Lightdash

Lightdash reads the dbt project, but we do not define metrics in Lightdash: MetricFlow owns every
definition. Build charts in the SQL Runner against the endorsed marts, so the numbers match the agent.

1. Create a BigQuery connection using the agent service account (it cannot read eval_truth).
2. Project source: dbt local, path /usr/app/dbt (mounted read-only by the compose file).
3. Create a space named Verified. Only data-team members can edit it. This is the endorsement analog.
4. SQL Runner charts:

ARR by motion, monthly
```sql
select month_start, motion, sum(arr_usd) as arr
from marts.fct_arr_monthly group by 1, 2 order by 1
```

Top 25 customers with health signals
```sql
with arr as (
  select customer_id, arr_usd from marts.fct_arr_monthly where month_start = '2026-09-01'),
use as (
  select customer_id,
         sum(if(usage_date >= '2026-08-16', base_traces, 0)) as traces_last_60d,
         sum(if(usage_date between '2026-06-17' and '2026-08-15', base_traces, 0)) as traces_prior_60d
  from marts.fct_daily_usage group by 1),
tix as (
  select customer_id, countif(priority in ('high','urgent') and created_date >= '2026-08-16') as hot_tickets_60d
  from marts.fct_support_tickets group by 1)
select c.customer_name, c.motion, c.region, c.deployment_type, a.arr_usd,
       safe_divide(u.traces_last_60d, u.traces_prior_60d) - 1 as traces_trend,
       coalesce(t.hot_tickets_60d, 0) as hot_tickets_60d
from arr a join marts.dim_customers c using (customer_id)
left join use u using (customer_id) left join tix t using (customer_id)
order by a.arr_usd desc limit 25
```

Upstream adoption (real PyPI data)
```sql
select date_trunc(download_date, week) as week, project, sum(downloads) as downloads
from marts.fct_pypi_downloads_daily group by 1, 2 order by 1
```

5. Save all three to a dashboard in the Verified space.
6. Commit the dashboard as code: `lightdash download --path lightdash/content` and check the YAML in.
