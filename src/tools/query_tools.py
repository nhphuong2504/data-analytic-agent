"""
Shared filtering and query helpers used by every analytics module.

The tier system applies progressive data-quality filters so that each
metric uses the correct subset of the cleaned transaction data.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Tier definitions (see docs/semantic_layer.md §2.5)
# ---------------------------------------------------------------------------
#   0 = raw            – everything, flags only
#   1 = no_adjustments – drop A-prefix adjustment rows
#   2 = standard       – tier 1 + drop zero/negative price, non-product codes
#   3 = revenue_safe   – tier 2 + drop cancellation rows
#   4 = customer_safe  – tier 3 + drop rows without Customer ID
# ---------------------------------------------------------------------------

TIER_NAMES: dict[int, str] = {
    0: "raw",
    1: "no_adjustments",
    2: "standard",
    3: "revenue_safe",
    4: "customer_safe",
}


def apply_tier(df: pd.DataFrame, tier: int) -> pd.DataFrame:
    """Return a copy of *df* filtered to the requested cleaning tier."""
    if tier < 0 or tier > 4:
        raise ValueError(f"tier must be 0-4, got {tier}")

    mask = pd.Series(True, index=df.index)

    if tier >= 1:
        mask &= ~df["is_adjustment"]

    if tier >= 2:
        mask &= ~df["is_zero_price"]
        mask &= ~df["is_negative_price"]
        mask &= df["is_product"]

    if tier >= 3:
        mask &= ~df["is_cancellation"]
        mask &= df["quantity"] > 0

    if tier >= 4:
        mask &= df["has_customer"]

    return df.loc[mask].copy()


def filter_period(
    df: pd.DataFrame,
    period: str | None = None,
    *,
    col: str = "invoice_month",
) -> pd.DataFrame:
    """Optionally narrow to a specific YYYY-MM period string."""
    if period is None:
        return df
    return df.loc[df[col] == period].copy()


def filter_country(
    df: pd.DataFrame,
    country: str | None = None,
) -> pd.DataFrame:
    """Optionally narrow to a single country."""
    if country is None:
        return df
    return df.loc[df["country"] == country].copy()
