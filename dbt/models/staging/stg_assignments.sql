select
    cast(customer_id as varchar)    as customer_id,
    cast(experiment_id as varchar)  as experiment_id,
    cast(variant as varchar)        as variant,
    cast(assigned_at as timestamp)  as assigned_at
from {{ source('raw', 'raw_assignments') }}
