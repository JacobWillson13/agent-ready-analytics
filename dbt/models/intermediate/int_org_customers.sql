-- Resolves every org to its billing customer and flags internal and secondary orgs.
with orgs as (
    select * from {{ ref('stg_app__organizations') }}
),

ranked as (
    select
        *,
        row_number() over (partition by account_id order by created_at, org_id) as org_rank_in_account
    from orgs
)

select
    r.org_id,
    coalesce(r.account_id, r.org_id)            as customer_id,
    r.account_id,
    m.metronome_customer_id,
    r.org_name,
    r.deployment_type,
    r.country,
    cr.region,
    r.is_internal,
    r.account_id is null or r.org_rank_in_account = 1 as is_primary_org,
    r.signup_date
from ranked r
left join {{ ref('stg_metronome__customers') }} m on r.org_id = m.org_id
left join {{ ref('country_regions') }} cr on r.country = cr.country
