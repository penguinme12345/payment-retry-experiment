from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from retrylab.sim.schemas import SCHEMAS


def test_all_tables_written_with_contract_schema(small_run: tuple[Path, dict[str, int]]) -> None:
    raw_dir, counts = small_run
    assert set(SCHEMAS) == set(counts)
    for table, schema in SCHEMAS.items():
        written = pq.read_schema(raw_dir / f"{table}.parquet")
        assert written.equals(schema, check_metadata=False), table
        assert pq.read_metadata(raw_dir / f"{table}.parquet").num_rows == counts[table]


def test_contract_column_names_and_types() -> None:
    expected = {
        "raw_customers": "customer_id:string signup_at:timestamp[us] country:string "
        "plan_tier:string monthly_price_usd:double card_brand:string card_funding:string "
        "payday_day_of_month:int32",
        "raw_assignments": "customer_id:string experiment_id:string variant:string "
        "assigned_at:timestamp[us]",
        "raw_invoices": "invoice_id:string customer_id:string amount_usd:double "
        "created_at:timestamp[us] is_experiment_invoice:bool status:string",
        "raw_payment_attempts": "attempt_id:string invoice_id:string attempt_number:int32 "
        "attempted_at:timestamp[us] outcome:string decline_code:string",
        "raw_support_tickets": "ticket_id:string customer_id:string created_at:timestamp[us] "
        "category:string",
        "raw_subscription_events": "customer_id:string event_type:string event_at:timestamp[us]",
    }
    for table, spec in expected.items():
        got = " ".join(f"{f.name}:{f.type}" for f in SCHEMAS[table])
        assert got == spec, table


def test_id_formats(small: dict[str, pd.DataFrame]) -> None:
    patterns = {
        ("raw_customers", "customer_id"): r"cus_\d{6}",
        ("raw_invoices", "invoice_id"): r"in_\d{7}",
        ("raw_payment_attempts", "attempt_id"): r"py_\d{8}",
        ("raw_support_tickets", "ticket_id"): r"tkt_\d{7}",
    }
    for (table, col), pat in patterns.items():
        values = small[table][col]
        assert values.is_unique, (table, col)
        assert values.map(lambda v, p=pat: re.fullmatch(p, v) is not None).all(), (table, col)
