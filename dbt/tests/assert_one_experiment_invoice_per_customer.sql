-- (a) Each customer has exactly one experiment invoice, and every assigned customer has one.
with per_customer as (
    select customer_id, count(*) as n
    from {{ ref('stg_invoices') }}
    where is_experiment_invoice
    group by customer_id
)
select a.customer_id, coalesce(p.n, 0) as n_experiment_invoices
from {{ ref('stg_assignments') }} as a
full outer join per_customer as p using (customer_id)
where coalesce(p.n, 0) <> 1 or a.customer_id is null
