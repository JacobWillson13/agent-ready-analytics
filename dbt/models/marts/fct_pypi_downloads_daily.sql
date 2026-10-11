select
    concat(project, '|', cast(download_date as string)) as project_day_id,
    project,
    download_date,
    downloads
from {{ ref('stg_pypi__downloads') }}
where download_date <= date('{{ var("as_of_date") }}')
