select project, cast(download_date as date) as download_date, downloads
from {{ source('pypi', 'daily_downloads') }}
