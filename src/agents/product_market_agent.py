"""
Product & Merchandising specialist — owns product performance, return
rates, basket analysis, and time-of-day patterns.

Responsibilities:
  - Product revenue, units sold, order frequency
  - Product return/cancellation rates
  - Top products by revenue and by volume
  - Basket size distribution
  - Country × product heatmap
  - Day-of-week and hourly revenue profiles

Default tier: 3 (revenue_safe) for positive-sales rankings;
drops to 2 when analysing return patterns that need cancellation rows.
"""

from __future__ import annotations

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent
from src.tools.query_tools import apply_tier, filter_country, filter_period


class ProductMarketAgent(BaseAgent):
    """Analyst focused on product mix, basket behaviour, and operations."""

    def __init__(self) -> None:
        super().__init__("MerchandisingOps")

    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
        top_n: int = 10,
    ) -> AgentResponse:
        t3 = filter_country(filter_period(apply_tier(df, 3), period), country)

        product_rev = (
            t3.groupby("stock_code")["line_revenue"]
            .sum()
            .sort_values(ascending=False)
        )
        top = product_rev.head(top_n)
        total_products = len(product_rev)

        return AgentResponse(
            agent_name=self.name,
            intent="product_performance",
            metrics_used=[
                "product_revenue",
                "top_products_by_revenue",
            ],
            data={
                "top_products_by_revenue": {
                    k: round(v, 2) for k, v in top.items()
                },
                "total_distinct_products": total_products,
            },
            summary=(
                f"Top {top_n} products account for "
                f"£{top.sum():,.2f} across {total_products:,} distinct products."
            ),
            caveats=[
                "Uses Tier 3 (revenue_safe): positive-quantity product rows only.",
            ],
            suggested_follow_ups=[
                "Which products have the highest return rate?",
                "What does the basket size distribution look like?",
                "How does the product mix vary by country?",
            ],
        )
