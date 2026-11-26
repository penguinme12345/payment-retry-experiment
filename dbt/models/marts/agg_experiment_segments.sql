-- One row per (variant, segment_dimension, segment_value) (contract C4).
{%- set dimensions = ['country', 'plan_tier', 'card_funding', 'initial_decline_code'] %}

{% for dim in dimensions %}
select
    variant,
    '{{ dim }}'                                                          as segment_dimension,
    cast({{ dim }} as varchar)                                           as segment_value,
    cast(count(*) as integer)                                            as n_invoices,
    cast(count(*) filter (where is_recovered) as integer)                as n_recovered,
    cast(avg(case when is_recovered then 1.0 else 0.0 end) as double)    as recovery_rate,
    cast(sum(recovered_amount_usd) / count(*) as double)                 as recovered_revenue_per_invoice_usd
from {{ ref('fct_experiment_invoices') }}
group by variant, {{ dim }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
