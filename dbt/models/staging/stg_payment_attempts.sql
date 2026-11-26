select
    cast(attempt_id as varchar)       as attempt_id,
    cast(invoice_id as varchar)       as invoice_id,
    cast(attempt_number as integer)   as attempt_number,
    cast(attempted_at as timestamp)   as attempted_at,
    cast(outcome as varchar)          as outcome,
    cast(decline_code as varchar)     as decline_code
from {{ source('raw', 'raw_payment_attempts') }}
