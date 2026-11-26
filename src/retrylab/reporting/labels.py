"""Plain-English labels for metrics and segments."""

from __future__ import annotations

COUNTRY_NAMES: dict[str, str] = {
    "US": "the US",
    "CA": "Canada",
    "GB": "the UK",
    "DE": "Germany",
    "FR": "France",
    "BR": "Brazil",
    "IN": "India",
    "AU": "Australia",
}

DECLINE_PHRASES: dict[str, str] = {
    "insufficient_funds": "declined for insufficient funds",
    "expired_card": "declined for an expired card",
    "do_not_honor": 'declined with a "do not honor" code',
    "generic_decline": "hit a generic decline",
}

DECLINE_SHORT: dict[str, str] = {
    "insufficient_funds": "insufficient-funds declines",
    "expired_card": "expired-card declines",
    "do_not_honor": "do-not-honor declines",
    "generic_decline": "generic declines",
}

METRIC_LABELS: dict[str, str] = {
    "recovery_rate": "recovery rate",
    "recovered_revenue_per_invoice_usd": "recovered revenue per failed invoice",
    "recovered_revenue_per_invoice": "recovered revenue per failed invoice",
    "recovered_revenue": "recovered revenue",
    "avg_retries_per_invoice": "retries per failed invoice",
    "billing_ticket_rate": "billing-complaint tickets within 14 days",
    "involuntary_churn_rate": "involuntary churn within 30 days",
    "experiment_invoices": "experiment invoices",
}

MONEY_METRICS = {"recovered_revenue_per_invoice_usd", "recovered_revenue_per_invoice"}
COUNT_METRICS = {"avg_retries_per_invoice"}


def metric_label(metric: str) -> str:
    """Human label for a metric name; falls back to the name with underscores as spaces."""
    return METRIC_LABELS.get(metric, metric.replace("_", " "))


def segment_subject(dimension: str, value: str) -> str:
    """The sentence subject for a segment, e.g. 'Customers declined for insufficient funds'."""
    if dimension == "initial_decline_code":
        phrase = DECLINE_PHRASES.get(value, f"with decline code {value}")
        return f"Customers {phrase}" if not phrase.startswith("hit") else f"Customers who {phrase}"
    if dimension == "country":
        return f"Customers in {COUNTRY_NAMES.get(value, value)}"
    if dimension == "plan_tier":
        return f"Customers on the {value.capitalize()} plan"
    if dimension == "card_funding":
        return f"Customers paying with a {value} card"
    return f"Customers with {dimension.replace('_', ' ')} = {value}"


def segment_short(dimension: str, value: str) -> str:
    """A short noun phrase for lists, e.g. 'insufficient-funds declines'."""
    if dimension == "initial_decline_code":
        return DECLINE_SHORT.get(value, f"{value.replace('_', ' ')} declines")
    if dimension == "country":
        return f"customers in {COUNTRY_NAMES.get(value, value)}"
    if dimension == "plan_tier":
        return f"{value.capitalize()}-plan customers"
    if dimension == "card_funding":
        return f"{value} cards"
    return f"{dimension.replace('_', ' ')} = {value}"


def join_list(items: list[str]) -> str:
    """Oxford-comma join: ['a', 'b', 'c'] -> 'a, b, and c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
