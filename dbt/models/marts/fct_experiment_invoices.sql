-- One row per experiment invoice (contract C4). Column names and types are fixed by the contract.
with invoices as (
    select * from {{ ref('stg_invoices') }} where is_experiment_invoice
),

attempts as (
    select * from {{ ref('int_invoice_attempts') }}
),

recovery as (
    select
        invoice_id,
        failed_at,
        initial_decline_code,
        retries_attempted,
        -- Recovered = a retry succeeded no later than failed_at + recovery_window_days (inclusive).
        case
            when first_retry_success_at <= failed_at + interval {{ var('recovery_window_days') }} day
                then first_retry_success_at
        end as recovered_at
    from attempts
)

select
    cast(i.invoice_id as varchar)                                   as invoice_id,
    cast(i.customer_id as varchar)                                  as customer_id,
    cast(asg.variant as varchar)                                    as variant,
    cast(c.country as varchar)                                      as country,
    cast(c.plan_tier as varchar)                                    as plan_tier,
    cast(c.card_funding as varchar)                                 as card_funding,
    cast(r.initial_decline_code as varchar)                         as initial_decline_code,
    cast(i.amount_usd as double)                                    as amount_usd,
    cast(r.failed_at as timestamp)                                  as failed_at,
    r.recovered_at is not null                                      as is_recovered,
    cast(r.recovered_at as timestamp)                               as recovered_at,
    cast(date_diff('second', r.failed_at, r.recovered_at) / 3600.0 as double)
                                                                    as hours_to_recovery,
    cast(coalesce(r.retries_attempted, 0) as integer)               as retries_attempted,
    cast(case when r.recovered_at is not null then i.amount_usd else 0 end as double)
                                                                    as recovered_amount_usd,
    coalesce(o.had_billing_ticket_14d, false)                       as had_billing_ticket_14d,
    coalesce(o.churned_involuntary_30d, false)                      as churned_involuntary_30d,
    cast(coalesce(p.pre_paid_invoice_count, 0) as integer)          as pre_paid_invoice_count,
    cast(coalesce(p.pre_failed_attempt_rate, 0) as double)          as pre_failed_attempt_rate
from invoices as i
left join recovery as r using (invoice_id)
left join {{ ref('stg_assignments') }} as asg
    on  asg.customer_id = i.customer_id
    and asg.experiment_id = '{{ var("experiment_id") }}'
left join {{ ref('stg_customers') }} as c on c.customer_id = i.customer_id
left join {{ ref('int_invoice_outcomes') }} as o on o.invoice_id = i.invoice_id
left join {{ ref('int_customer_pre_period') }} as p on p.customer_id = i.customer_id
