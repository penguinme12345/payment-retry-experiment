-- (b) recovered_amount_usd is 0 when not recovered, and equals amount_usd when recovered.
select invoice_id, is_recovered, amount_usd, recovered_amount_usd
from {{ ref('fct_experiment_invoices') }}
where (not is_recovered and recovered_amount_usd <> 0)
   or (is_recovered and recovered_amount_usd <> amount_usd)
   or (not is_recovered and (recovered_at is not null or hours_to_recovery is not null))
