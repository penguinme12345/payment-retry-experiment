select
    cast(customer_id as varchar)  as customer_id,
    cast(event_type as varchar)   as event_type,
    cast(event_at as timestamp)   as event_at
from {{ source('raw', 'raw_subscription_events') }}
