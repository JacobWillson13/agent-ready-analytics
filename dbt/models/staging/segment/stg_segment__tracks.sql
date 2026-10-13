{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'event_date', 'data_type': 'date'},
    cluster_by=['org_id'],
    on_schema_change='append_new_columns'
) }}

-- Duplicates share a message id and timestamp, so they always land in the same
-- partition; dedupe within the rebuilt partitions is complete.
with source as (
    select *
    from {{ source('segment', 'tracks') }}
    {% if is_incremental() %}
    where date(timestamp) >= date_sub(_dbt_max_partition, interval 3 day)
    {% endif %}
)

select
    id                  as event_id,
    user_id,
    org_id,
    event               as event_name,
    timestamp           as event_at,
    date(timestamp)     as event_date,
    received_at
from source
qualify row_number() over (partition by id order by received_at) = 1
