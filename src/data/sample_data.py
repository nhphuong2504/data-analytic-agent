"""
Synthetic sample data generator for demo and testing.

Produces a DataFrame with the same schema as the cleaned Online Retail II
dataset so that the Streamlit app and agents can run without the real file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_sample(n_rows: int = 20_000, seed: int = 42) -> pd.DataFrame:
    """Return a synthetic cleaned-schema DataFrame.

    The data is intentionally realistic enough to exercise every agent:
    - Multiple countries (UK dominant, ~80 %)
    - Cancellation rows (~3 %)
    - Missing customer IDs (~20 %)
    - Realistic price / quantity distributions
    - Date range spanning 2010-12 to 2011-12
    """
    rng = np.random.default_rng(seed)

    countries = [
        "United Kingdom", "France", "Germany", "Spain", "Netherlands",
        "Belgium", "Portugal", "Italy", "Australia", "Japan",
    ]
    country_weights = [0.80, 0.04, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.015, 0.015]

    start = pd.Timestamp("2010-12-01")
    end = pd.Timestamp("2011-12-09")
    dates = pd.to_datetime(
        rng.integers(start.value, end.value, size=n_rows),
    )

    n_customers = int(n_rows * 0.25)
    customer_pool = rng.integers(12000, 12000 + n_customers, size=n_rows)

    missing_mask = rng.random(n_rows) < 0.20
    customer_ids = pd.array(customer_pool, dtype="Int64")
    customer_ids[missing_mask] = pd.NA

    n_products = 500
    stock_pool = [f"{rng.integers(10000, 99999)}{chr(65 + i % 26)}" for i in range(n_products)]

    cancel_mask = rng.random(n_rows) < 0.03
    invoices = []
    inv_counter = 536365
    for is_cancel in cancel_mask:
        prefix = "C" if is_cancel else ""
        invoices.append(f"{prefix}{inv_counter}")
        inv_counter += 1

    non_product_indices = rng.choice(n_rows, size=int(n_rows * 0.01), replace=False)

    stock_codes = rng.choice(stock_pool, size=n_rows).tolist()
    for idx in non_product_indices:
        stock_codes[idx] = rng.choice(["POST", "DOT", "D", "M", "BANK CHARGES"])

    quantities = rng.integers(1, 50, size=n_rows).astype("int64")
    quantities[cancel_mask] = -quantities[cancel_mask]

    prices = np.round(rng.lognormal(mean=1.0, sigma=0.8, size=n_rows), 2).clip(0.01, 500.0)

    zero_price_idx = rng.choice(n_rows, size=int(n_rows * 0.005), replace=False)
    prices[zero_price_idx] = 0.0

    descriptions = [f"PRODUCT {sc}" for sc in stock_codes]
    for idx in non_product_indices:
        descriptions[idx] = stock_codes[idx]

    import re
    from src.data.schema import NON_PRODUCT_PATTERN, OUTLIER_REVENUE_THRESHOLD

    df = pd.DataFrame({
        "invoice": invoices,
        "stock_code": [s.upper() for s in stock_codes],
        "description": descriptions,
        "quantity": quantities,
        "invoice_date": dates,
        "price": prices,
        "customer_id": customer_ids,
        "country": rng.choice(countries, size=n_rows, p=country_weights).tolist(),
    })

    df["line_revenue"] = df["quantity"] * df["price"]
    df["is_cancellation"] = df["invoice"].str.startswith("C")
    df["is_adjustment"] = df["invoice"].str.startswith("A")

    _non_product = re.compile(NON_PRODUCT_PATTERN)
    df["is_product"] = ~df["stock_code"].apply(lambda x: bool(_non_product.match(x)))

    df["has_customer"] = df["customer_id"].notna()
    df["is_zero_price"] = df["price"] == 0.0
    df["is_negative_price"] = df["price"] < 0.0
    df["is_outlier_revenue"] = df["line_revenue"].abs() > OUTLIER_REVENUE_THRESHOLD

    df["invoice_year"] = df["invoice_date"].dt.year
    df["invoice_month"] = df["invoice_date"].dt.to_period("M").astype(str)
    df["invoice_dow"] = df["invoice_date"].dt.dayofweek
    df["invoice_hour"] = df["invoice_date"].dt.hour

    return df
