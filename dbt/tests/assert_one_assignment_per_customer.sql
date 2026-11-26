-- (e) Every customer has exactly one assignment, and every assignment points at a customer.
with per_customer as (
    select customer_id, count(*) as n
    from {{ ref('stg_assignments') }}
    group by customer_id
)
select c.customer_id, coalesce(p.n, 0) as n_assignments
from {{ ref('stg_customers') }} as c
full outer join per_customer as p using (customer_id)
where coalesce(p.n, 0) <> 1 or c.customer_id is null
