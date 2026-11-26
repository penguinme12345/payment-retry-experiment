-- One row per variant (contract C4). Rates use experiment invoices as the denominator.
select
    variant,
    cast(count(*) as integer)                                            as n_invoices,
    cast(count(*) filter (where is_recovered) as integer)                as n_recovered,
    cast(avg(case when is_recovered then 1.0 else 0.0 end) as double)    as recovery_rate,
    cast(round(sum(recovered_amount_usd), 2) as double)                  as recovered_revenue_usd,
    cast(sum(recovered_amount_usd) / count(*) as double)                 as recovered_revenue_per_invoice_usd,
    cast(avg(retries_attempted) as double)                               as avg_retries_per_invoice,
    cast(avg(case when had_billing_ticket_14d then 1.0 else 0.0 end) as double)
                                                                         as billing_ticket_rate,
    cast(avg(case when churned_involuntary_30d then 1.0 else 0.0 end) as double)
                                                                         as involuntary_churn_rate
from {{ ref('fct_experiment_invoices') }}
group by variant
order by variant
