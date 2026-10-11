-- One row per calendar month in the data window with its as-of date.
select
    month_start,
    least(last_day(month_start, month), date('{{ var("as_of_date") }}')) as as_of_date
from unnest(generate_date_array(
    date('{{ var("data_start_date") }}'),
    date_trunc(date('{{ var("as_of_date") }}'), month),
    interval 1 month
)) as month_start
