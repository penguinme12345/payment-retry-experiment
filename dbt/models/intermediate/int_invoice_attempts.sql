-- Per-invoice rollup of charge attempts. One row per invoice that has at least one attempt.
-- Recovery-window logic lives in fct_experiment_invoices; this model only summarises attempts.
with attempts as (
    select * from {{ ref('stg_payment_attempts') }}
),

rolled as (
    select
        invoice_id,
        min(case when attempt_number = 0 then attempted_at end)          as failed_at,
        max(case when attempt_number = 0 then decline_code end)          as initial_decline_code,
        bool_or(attempt_number = 0 and outcome = 'failed')               as initial_attempt_failed,
        count(*)                                                         as n_attempts,
        count(*) filter (where outcome = 'failed')                       as n_failed_attempts,
        count(*) filter (where attempt_number >= 1)                      as retries_attempted,
        min(attempted_at) filter (where outcome = 'succeeded')           as first_success_at,
        min(case when outcome = 'succeeded' and attempt_number >= 1
                 then attempted_at end)                                  as first_retry_success_at
    from attempts
    group by invoice_id
)

select
    invoice_id,
    failed_at,
    initial_decline_code,
    coalesce(initial_attempt_failed, false)    as initial_attempt_failed,
    cast(n_attempts as integer)                as n_attempts,
    cast(n_failed_attempts as integer)         as n_failed_attempts,
    cast(retries_attempted as integer)         as retries_attempted,
    first_success_at,
    first_retry_success_at
from rolled
