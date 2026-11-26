-- Customer-experience outcomes for each experiment invoice, measured from the initial failure
-- (attempt 0). Windows are [failed_at, failed_at + N days], both ends inclusive.
with experiment_invoices as (
    select i.invoice_id, i.customer_id, a.failed_at
    from {{ ref('stg_invoices') }} as i
    inner join {{ ref('int_invoice_attempts') }} as a using (invoice_id)
    where i.is_experiment_invoice
),

billing_tickets as (
    select e.invoice_id, count(*) as n_billing_tickets
    from experiment_invoices as e
    inner join {{ ref('stg_support_tickets') }} as t
        on  t.customer_id = e.customer_id
        and t.category = 'billing_complaint'
        and t.created_at >= e.failed_at
        and t.created_at <= e.failed_at + interval {{ var('ticket_window_days') }} day
    group by e.invoice_id
),

involuntary_churn as (
    select e.invoice_id, min(s.event_at) as churned_at
    from experiment_invoices as e
    inner join {{ ref('stg_subscription_events') }} as s
        on  s.customer_id = e.customer_id
        and s.event_type = 'churned_involuntary'
        and s.event_at >= e.failed_at
        and s.event_at <= e.failed_at + interval {{ var('churn_window_days') }} day
    group by e.invoice_id
)

select
    e.invoice_id,
    e.customer_id,
    e.failed_at,
    cast(coalesce(bt.n_billing_tickets, 0) as integer)   as n_billing_tickets_14d,
    coalesce(bt.n_billing_tickets, 0) > 0                as had_billing_ticket_14d,
    ic.churned_at                                        as churned_involuntary_at,
    ic.churned_at is not null                            as churned_involuntary_30d
from experiment_invoices as e
left join billing_tickets as bt using (invoice_id)
left join involuntary_churn as ic using (invoice_id)
