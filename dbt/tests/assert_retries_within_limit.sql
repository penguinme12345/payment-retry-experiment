-- (c) No invoice has more than max_retries (4) retries.
select invoice_id, retries_attempted
from {{ ref('fct_experiment_invoices') }}
where retries_attempted > {{ var('max_retries') }} or retries_attempted < 0
