select
    cast(id as string)                  as release_id,
    repo,
    tag_name,
    name                                as release_name,
    prerelease                          as is_prerelease,
    cast(published_at as timestamp)     as published_at
from {{ source('github', 'releases') }}
