select
    t.ticket_id,
    o.customer_id,
    t.org_id,
    o.current_plan,
    t.priority,
    t.status,
    t.category,
    t.created_at,
    date(t.created_at)          as created_date,
    t.solved_at,
    t.hours_to_resolution
from {{ ref('stg_support__tickets') }} t
join {{ ref('dim_orgs') }} o on t.org_id = o.org_id
where not o.is_internal
