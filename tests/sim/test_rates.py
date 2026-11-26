"""Statistical checks on the full 50k-customer default run (contract PRD-A section 4)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.slow


def _rates(exp: pd.DataFrame) -> pd.DataFrame:
    return exp.groupby(["decline_code", "variant"]).is_recovered.mean().unstack()


def test_control_recovery_matches_baseline(
    full_exp: pd.DataFrame, ground_truth: dict[str, Any]
) -> None:
    rates = _rates(full_exp)
    for code, base in ground_truth["baseline_recovery"].items():
        assert rates.loc[code, "control"] == pytest.approx(base, abs=0.015), code


def test_treatment_lift_matches_configured(
    full_exp: pd.DataFrame, ground_truth: dict[str, Any]
) -> None:
    rates = _rates(full_exp)
    for code, lift in ground_truth["treatment_lift_abs"].items():
        observed = rates.loc[code, "treatment"] - rates.loc[code, "control"]
        assert observed == pytest.approx(lift, abs=0.02), code


def test_assignment_split(full: dict[str, pd.DataFrame]) -> None:
    share = (full["raw_assignments"].variant == "treatment").mean()
    assert 0.49 <= share <= 0.51


def test_cuped_covariate_is_predictive(full_exp: pd.DataFrame) -> None:
    corr = np.corrcoef(full_exp.pre_failed_attempt_rate, full_exp.is_recovered)[0, 1]
    assert -0.35 <= corr <= -0.20


def test_pre_period_initial_failure_rate(full: dict[str, pd.DataFrame]) -> None:
    inv, att = full["raw_invoices"], full["raw_payment_attempts"]
    pre_ids = inv.invoice_id[~inv.is_experiment_invoice]
    a0 = att[(att.attempt_number == 0) & att.invoice_id.isin(pre_ids)]
    assert 0.03 <= (a0.outcome == "failed").mean() <= 0.10
    assert (inv.status[~inv.is_experiment_invoice] == "paid").mean() > 0.97


def test_guardrail_rates(
    full: dict[str, pd.DataFrame], full_exp: pd.DataFrame, ground_truth: dict[str, Any]
) -> None:
    tk = full["raw_support_tickets"]
    billing = set(tk.customer_id[tk.category == "billing_complaint"])
    had = full_exp.index.isin(list(billing))
    by_variant = pd.Series(had, index=full_exp.index).groupby(full_exp.variant).mean()
    for v, rate in ground_truth["billing_ticket_rate"].items():
        assert by_variant[v] == pytest.approx(rate, abs=0.005)

    ev = full["raw_subscription_events"]
    invol = set(ev.customer_id[ev.event_type == "churned_involuntary"])
    unrec = full_exp[~full_exp.is_recovered]
    share = unrec.index.isin(list(invol)).mean()
    assert share == pytest.approx(ground_truth["involuntary_churn_given_unrecovered"], abs=0.02)
