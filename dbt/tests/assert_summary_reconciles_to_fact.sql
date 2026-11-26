-- (d) agg_experiment_summary totals reconcile to fct_experiment_invoices, per variant and overall,
-- and each segment dimension in agg_experiment_segments sums back to the same totals.
with fact as (
    select
        variant,
        count(*)                                     as n_invoices,
        count(*) filter (where is_recovered)         as n_recovered,
        round(sum(recovered_amount_usd), 2)          as recovered_revenue_usd,
        sum(retries_attempted)                       as retries,
        count(*) filter (where had_billing_ticket_14d)  as n_tickets,
        count(*) filter (where churned_involuntary_30d) as n_churned
    from {{ ref('fct_experiment_invoices') }}
    group by variant
),

summary_check as (
    select f.variant, 'summary' as source
    from fact as f
    full outer join {{ ref('agg_experiment_summary') }} as s using (variant)
    where s.variant is null or f.variant is null
       or s.n_invoices <> f.n_invoices
       or s.n_recovered <> f.n_recovered
       or abs(s.recovered_revenue_usd - f.recovered_revenue_usd) > 0.005
       or abs(s.recovery_rate - f.n_recovered::double / f.n_invoices) > 1e-12
       or abs(s.avg_retries_per_invoice - f.retries::double / f.n_invoices) > 1e-12
       or abs(s.billing_ticket_rate - f.n_tickets::double / f.n_invoices) > 1e-12
       or abs(s.involuntary_churn_rate - f.n_churned::double / f.n_invoices) > 1e-12
),

segment_totals as (
    select variant, segment_dimension, sum(n_invoices) as n_invoices,
           sum(n_recovered) as n_recovered
    from {{ ref('agg_experiment_segments') }}
    group by variant, segment_dimension
),

segment_check as (
    select st.variant, 'segments:' || st.segment_dimension as source
    from segment_totals as st
    left join fact as f using (variant)
    where f.variant is null
       or st.n_invoices <> f.n_invoices
       or st.n_recovered <> f.n_recovered
)

select * from summary_check
union all
select * from segment_check
