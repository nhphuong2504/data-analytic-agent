"""
Customer Insight specialist — owns customer counts, segmentation,
retention, repeat-purchase, CLV proxy, and concentration metrics.

Responsibilities:
  - Unique / new / returning customer counts
  - Customer retention rate, repeat purchase rate
  - Average orders per customer, CLV proxy
  - Top-customer concentration (revenue share of top-N)
  - Customer country mix
  - RFM (recency, frequency, monetary) and segment labels

Default tier: 4 (customer_safe) — all metrics require known customer IDs.
Coverage caveat: ~23% of rows lack a customer ID and are excluded.
"""

from __future__ import annotations

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent
from src.tools.query_tools import apply_tier, filter_country, filter_period


class CustomerInsightAgent(BaseAgent):
    """Analyst focused on customer behaviour and segmentation."""

    def __init__(self) -> None:
        super().__init__("CustomerAnalytics")

    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> AgentResponse:
        t4 = filter_country(filter_period(apply_tier(df, 4), period), country)

        unique_cust = int(t4["customer_id"].nunique())
        order_ct = int(t4["invoice"].nunique())
        avg_orders = order_ct / unique_cust if unique_cust else 0.0

        return AgentResponse(
            agent_name=self.name,
            intent="customer_value",
            metrics_used=[
                "unique_customers",
                "avg_orders_per_customer",
            ],
            data={
                "unique_customers": unique_cust,
                "order_count": order_ct,
                "avg_orders_per_customer": round(avg_orders, 2),
            },
            summary=(
                f"{unique_cust:,} unique customers placed {order_ct:,} orders "
                f"(avg {avg_orders:.1f} orders per customer)."
            ),
            caveats=[
                "Uses Tier 4 (customer_safe): excludes rows without Customer ID (~23% of data).",
            ],
            suggested_follow_ups=[
                "What does the RFM segmentation look like?",
                "What is the repeat purchase rate?",
                "How concentrated is revenue among top customers?",
            ],
        )
