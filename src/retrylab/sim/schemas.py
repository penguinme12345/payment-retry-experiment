"""PyArrow schemas for the raw tables (contract C3)."""

from __future__ import annotations

import pyarrow as pa

TS = pa.timestamp("us")

RAW_CUSTOMERS = pa.schema(
    [
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("signup_at", TS, nullable=False),
        pa.field("country", pa.string(), nullable=False),
        pa.field("plan_tier", pa.string(), nullable=False),
        pa.field("monthly_price_usd", pa.float64(), nullable=False),
        pa.field("card_brand", pa.string(), nullable=False),
        pa.field("card_funding", pa.string(), nullable=False),
        pa.field("payday_day_of_month", pa.int32(), nullable=True),
    ]
)

RAW_ASSIGNMENTS = pa.schema(
    [
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("experiment_id", pa.string(), nullable=False),
        pa.field("variant", pa.string(), nullable=False),
        pa.field("assigned_at", TS, nullable=False),
    ]
)

RAW_INVOICES = pa.schema(
    [
        pa.field("invoice_id", pa.string(), nullable=False),
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("amount_usd", pa.float64(), nullable=False),
        pa.field("created_at", TS, nullable=False),
        pa.field("is_experiment_invoice", pa.bool_(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
    ]
)

RAW_PAYMENT_ATTEMPTS = pa.schema(
    [
        pa.field("attempt_id", pa.string(), nullable=False),
        pa.field("invoice_id", pa.string(), nullable=False),
        pa.field("attempt_number", pa.int32(), nullable=False),
        pa.field("attempted_at", TS, nullable=False),
        pa.field("outcome", pa.string(), nullable=False),
        pa.field("decline_code", pa.string(), nullable=True),
    ]
)

RAW_SUPPORT_TICKETS = pa.schema(
    [
        pa.field("ticket_id", pa.string(), nullable=False),
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("created_at", TS, nullable=False),
        pa.field("category", pa.string(), nullable=False),
    ]
)

RAW_SUBSCRIPTION_EVENTS = pa.schema(
    [
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("event_at", TS, nullable=False),
    ]
)

SCHEMAS: dict[str, pa.Schema] = {
    "raw_customers": RAW_CUSTOMERS,
    "raw_assignments": RAW_ASSIGNMENTS,
    "raw_invoices": RAW_INVOICES,
    "raw_payment_attempts": RAW_PAYMENT_ATTEMPTS,
    "raw_support_tickets": RAW_SUPPORT_TICKETS,
    "raw_subscription_events": RAW_SUBSCRIPTION_EVENTS,
}
