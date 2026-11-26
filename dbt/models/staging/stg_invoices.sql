select
    cast(invoice_id as varchar)             as invoice_id,
    cast(customer_id as varchar)            as customer_id,
    cast(amount_usd as double)              as amount_usd,
    cast(created_at as timestamp)           as created_at,
    cast(is_experiment_invoice as boolean)  as is_experiment_invoice,
    cast(status as varchar)                 as status
from {{ source('raw', 'raw_invoices') }}
