select
    cast(customer_id as varchar)          as customer_id,
    cast(signup_at as timestamp)          as signup_at,
    cast(country as varchar)              as country,
    cast(plan_tier as varchar)            as plan_tier,
    cast(monthly_price_usd as double)     as monthly_price_usd,
    cast(card_brand as varchar)           as card_brand,
    cast(card_funding as varchar)         as card_funding,
    cast(payday_day_of_month as integer)  as payday_day_of_month
from {{ source('raw', 'raw_customers') }}
