"""
Data Quality specialist — audits raw data for completeness and anomalies.

Responsibilities:
  - Missing customer ID percentage
  - Missing description percentage
  - Zero-price and negative-price row counts
  - Cancellation row percentage
  - Non-product row percentage
  - Outlier revenue row count

Called as a pre-check before other specialists to produce caveats that
are prepended to answers.  Uses Tier 0 (raw) data exclusively.
"""

from __future__ import annotations

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent
from src.tools.query_tools import filter_period


class DataQualityAgent(BaseAgent):
    """Guardian agent that reports data health before analysis."""

    def __init__(self) -> None:
        super().__init__("DataQuality")

    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> AgentResponse:
        subset = filter_period(df, period)
        n = len(subset)
        if n == 0:
            return AgentResponse(
                agent_name=self.name,
                intent="data_quality",
                summary="No rows found for the requested period.",
                caveats=["Empty dataset for the given filters."],
            )

        missing_cust = float((~subset["has_customer"]).sum() / n)
        missing_desc = float(subset["description"].isna().sum() / n)
        zero_price = float(subset["is_zero_price"].sum() / n)
        neg_price = float(subset["is_negative_price"].sum() / n)
        cancel = float(subset["is_cancellation"].sum() / n)
        non_product = float((~subset["is_product"]).sum() / n)
        outliers = int(subset["is_outlier_revenue"].sum())

        data = {
            "missing_customer_pct": round(missing_cust, 4),
            "missing_description_pct": round(missing_desc, 4),
            "zero_price_pct": round(zero_price, 4),
            "negative_price_pct": round(neg_price, 4),
            "cancellation_pct": round(cancel, 4),
            "non_product_pct": round(non_product, 4),
            "outlier_revenue_count": outliers,
            "total_rows": n,
        }

        caveats = []
        if missing_cust > 0.05:
            caveats.append(f"{missing_cust:.1%} of rows lack a Customer ID.")
        if cancel > 0.01:
            caveats.append(f"{cancel:.1%} of rows are cancellations.")
        if zero_price > 0.005:
            caveats.append(f"{zero_price:.1%} of rows have zero price.")
        if outliers > 0:
            caveats.append(f"{outliers} rows have |line_revenue| > threshold.")

        return AgentResponse(
            agent_name=self.name,
            intent="data_quality",
            metrics_used=list(data.keys()),
            data=data,
            summary=(
                f"Data quality: {n:,} rows, "
                f"{missing_cust:.1%} missing customer, "
                f"{cancel:.1%} cancellations, "
                f"{outliers} revenue outliers."
            ),
            caveats=caveats,
            suggested_follow_ups=[
                "Which months have the most missing customer IDs?",
                "Are zero-price rows concentrated in specific products?",
            ],
        )
