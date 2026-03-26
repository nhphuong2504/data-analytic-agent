"""
Cleaning pipeline: raw DataFrame → analysis-ready DataFrame.

Applies the transformations specified in ``docs/semantic_layer.md §2``:
  - type casting and column renaming (already done in ``load_raw``)
  - derived columns: ``line_revenue``, boolean flags, date grains
  - country normalisation
  - outlier flagging

The output matches the ``CLEAN_COLUMNS`` schema in ``src.data.schema``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.data.schema import (
    COUNTRY_NORMALIZATION,
    EXPECTED_COLUMN_NAMES,
    NON_PRODUCT_PATTERN,
    OUTLIER_REVENUE_THRESHOLD,
)

_PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
_PARQUET_PATH = _PROCESSED_DIR / "transactions_clean.parquet"


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all cleaning transformations and return the canonical schema."""
    out = df.copy()

    out["invoice"] = out["invoice"].astype(str).str.strip()
    out["stock_code"] = out["stock_code"].astype(str).str.strip().str.upper()

    if "description" in out.columns:
        out["description"] = out["description"].astype(str).where(
            out["description"].notna(), other=None,
        )

    out["invoice_date"] = pd.to_datetime(out["invoice_date"], errors="coerce")

    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(0).astype("int64")
    out["price"] = pd.to_numeric(out["price"], errors="coerce").fillna(0.0).astype("float64")

    if "customer_id" in out.columns:
        out["customer_id"] = pd.to_numeric(out["customer_id"], errors="coerce").astype("Int64")

    out["country"] = out["country"].replace(COUNTRY_NORMALIZATION)

    out["line_revenue"] = out["quantity"] * out["price"]

    out["is_cancellation"] = out["invoice"].str.startswith("C")
    out["is_adjustment"] = out["invoice"].str.startswith("A")

    _non_product = re.compile(NON_PRODUCT_PATTERN)
    out["is_product"] = ~out["stock_code"].apply(lambda x: bool(_non_product.match(x)))

    out["has_customer"] = out["customer_id"].notna()

    out["is_zero_price"] = out["price"] == 0.0
    out["is_negative_price"] = out["price"] < 0.0

    out["is_outlier_revenue"] = out["line_revenue"].abs() > OUTLIER_REVENUE_THRESHOLD

    out["invoice_year"] = out["invoice_date"].dt.year
    out["invoice_month"] = out["invoice_date"].dt.to_period("M").astype(str)
    out["invoice_dow"] = out["invoice_date"].dt.dayofweek
    out["invoice_hour"] = out["invoice_date"].dt.hour

    return out


def save_parquet(df: pd.DataFrame, path: Path | str | None = None) -> Path:
    """Write cleaned DataFrame to Parquet and return the path."""
    dest = Path(path) if path is not None else _PARQUET_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest, index=False)
    return dest


def load_clean(path: Path | str | None = None) -> pd.DataFrame:
    """Read a previously saved clean Parquet file."""
    src = Path(path) if path is not None else _PARQUET_PATH
    if not src.exists():
        raise FileNotFoundError(
            f"Cleaned Parquet not found at {src}. "
            "Run the cleaning pipeline first or use sample data."
        )
    return pd.read_parquet(src)
