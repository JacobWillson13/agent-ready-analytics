-- Fails if deduplicated events, active users, or traces differ from the answer key on any org-day.
with truth as (
    select org_id, cast(date as date) as usage_date, traces, events, active_users
    from {{ source('eval_truth', 'truth_org_daily') }}
    where not is_internal
)
select t.org_id, t.usage_date
from truth t
left join {{ ref('fct_daily_usage') }} m on t.org_id = m.org_id and t.usage_date = m.usage_date
where coalesce(m.base_traces, 0) != t.traces
   or coalesce(m.product_events, 0) != t.events
   or coalesce(m.active_users, 0) != t.active_users
