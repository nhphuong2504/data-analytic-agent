"""
Executive KPI specialist — owns revenue, order, geographic, and time-series
metrics from the catalog.

Responsibilities:
  - Total/net/cancellation revenue and rates
  - Order counts, AOV, average items per order, average unit price
  - Revenue per customer (requires Tier 4)
  - Revenue and order counts by country, country share
  - Monthly revenue, monthly order counts, MoM/YoY growth, seasonal index

Default tier: 3 (revenue_safe) for most metrics; drops to 2 for
cancellation-inclusive metrics and rises to 4 for per-customer metrics.
"""

from __future__ import annotations

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent
from src.tools.query_tools import apply_tier, filter_country, filter_period


class ExecutiveKpiAgent(BaseAgent):
    """Analyst that computes headline KPIs and trend summaries."""

    def __init__(self) -> None:
        super().__init__("KpiStrategy")

    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> AgentResponse:
        t3 = filter_country(filter_period(apply_tier(df, 3), period), country)

        gross_rev = float(t3["line_revenue"].sum())
        order_ct = int(t3["invoice"].nunique())
        aov = gross_rev / order_ct if order_ct else 0.0

        return AgentResponse(
            agent_name=self.name,
            intent="revenue_overview",
            metrics_used=[
                "total_gross_revenue",
                "order_count",
                "avg_order_value",
            ],
            data={
                "total_gross_revenue": round(gross_rev, 2),
                "order_count": order_ct,
                "avg_order_value": round(aov, 2),
            },
            summary=(
                f"Gross revenue: £{gross_rev:,.2f} across {order_ct:,} orders "
                f"(AOV £{aov:,.2f})."
            ),
            caveats=_build_caveats(period, country),
            suggested_follow_ups=[
                "How does this compare month-over-month?",
                "Which countries drive the most revenue?",
                "What is the cancellation rate?",
            ],
        )


def _build_caveats(period: str | None, country: str | None) -> list[str]:
    caveats: list[str] = ["Uses Tier 3 (revenue_safe): excludes cancellations, zero/negative prices, non-product rows."]
    if period:
        caveats.append(f"Filtered to period {period}.")
    if country:
        caveats.append(f"Filtered to country {country}.")
    return caveats
