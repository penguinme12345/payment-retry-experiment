-- CUPED covariates: each customer's billing history in the pre-period (C2), both dates inclusive.
-- Every customer gets a row; customers with no pre-period history get zeros.
with pre_invoices as (
    select *
    from {{ ref('stg_invoices') }}
    where not is_experiment_invoice
      and created_at >= cast('{{ var("pre_period_start") }}' as timestamp)
      and created_at <  cast('{{ var("pre_period_end") }}' as date) + interval 1 day
),

invoice_counts as (
    select
        customer_id,
        count(*)                                     as pre_invoice_count,
        count(*) filter (where status = 'paid')      as pre_paid_invoice_count
    from pre_invoices
    group by customer_id
),

attempt_counts as (
    select
        i.customer_id,
        count(*)                                     as pre_attempt_count,
        count(*) filter (where a.outcome = 'failed') as pre_failed_attempt_count
    from pre_invoices as i
    inner join {{ ref('stg_payment_attempts') }} as a using (invoice_id)
    group by i.customer_id
)

select
    c.customer_id,
    cast(coalesce(ic.pre_invoice_count, 0) as integer)          as pre_invoice_count,
    cast(coalesce(ic.pre_paid_invoice_count, 0) as integer)     as pre_paid_invoice_count,
    cast(coalesce(ac.pre_attempt_count, 0) as integer)          as pre_attempt_count,
    cast(coalesce(ac.pre_failed_attempt_count, 0) as integer)   as pre_failed_attempt_count,
    case
        when coalesce(ac.pre_attempt_count, 0) = 0 then 0.0
        else ac.pre_failed_attempt_count::double / ac.pre_attempt_count
    end                                                         as pre_failed_attempt_rate
from {{ ref('stg_customers') }} as c
left join invoice_counts as ic using (customer_id)
left join attempt_counts as ac using (customer_id)
