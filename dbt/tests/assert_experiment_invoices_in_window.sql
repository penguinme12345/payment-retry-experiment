-- Every experiment invoice failed inside the experiment window (C2), with attempt 0 failed.
select f.invoice_id, f.failed_at
from {{ ref('fct_experiment_invoices') }} as f
inner join {{ ref('int_invoice_attempts') }} as a using (invoice_id)
where not a.initial_attempt_failed
   or f.failed_at < cast('{{ var("experiment_start") }}' as timestamp)
   or f.failed_at >= cast('{{ var("experiment_end") }}' as date) + interval 1 day
