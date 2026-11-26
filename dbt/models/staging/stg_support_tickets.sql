select
    cast(ticket_id as varchar)     as ticket_id,
    cast(customer_id as varchar)   as customer_id,
    cast(created_at as timestamp)  as created_at,
    cast(category as varchar)      as category
from {{ source('raw', 'raw_support_tickets') }}
