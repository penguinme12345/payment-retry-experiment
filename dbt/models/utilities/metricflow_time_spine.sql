-- Daily time spine required by MetricFlow.
select cast(range as date) as date_day
from range(
    cast('{{ var("time_spine_start") }}' as date),
    cast('{{ var("time_spine_end") }}' as date) + interval 1 day,
    interval 1 day
)
