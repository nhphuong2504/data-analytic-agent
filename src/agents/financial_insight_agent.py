"""
Financial Insights specialist — owns cohort analysis, unit economics,
postage ratios, and non-UK revenue share.

Responsibilities:
  - Cohort revenue (revenue by first-purchase month cohort)
  - Cohort retention matrix
  - Revenue per invoice line
  - Postage as a percentage of gross revenue
  - Non-UK revenue share

Default tier: 4 for cohort metrics (need customer IDs); drops to 0/3
for postage and non-UK calculations that don't require customer identity.
"""

from __future__ import annotations

import pandas as pd

from src.agents.base import AgentResponse, BaseAgent
from src.tools.query_tools import apply_tier, filter_country, filter_period


class FinancialInsightAgent(BaseAgent):
    """Analyst focused on cohort value, unit economics, and cost ratios."""

    def __init__(self) -> None:
        super().__init__("FinancialInsights")

    def build_context(
        self,
        df: pd.DataFrame,
        question: str,
        *,
        period: str | None = None,
        country: str | None = None,
    ) -> AgentResponse:
        t3 = filter_period(apply_tier(df, 3), period)

        gross_rev = float(t3["line_revenue"].sum())
        row_count = len(t3)
        rev_per_line = gross_rev / row_count if row_count else 0.0

        non_uk = t3.loc[t3["country"] != "United Kingdom", "line_revenue"].sum()
        non_uk_share = non_uk / gross_rev if gross_rev else 0.0

        return AgentResponse(
            agent_name=self.name,
            intent="financial_analysis",
            metrics_used=[
                "revenue_per_invoice_line",
                "non_uk_revenue_share",
            ],
            data={
                "revenue_per_invoice_line": round(rev_per_line, 2),
                "non_uk_revenue_share": round(non_uk_share, 4),
            },
            summary=(
                f"Revenue per line item: £{rev_per_line:,.2f}. "
                f"Non-UK revenue share: {non_uk_share:.1%}."
            ),
            caveats=[
                "Revenue per line uses Tier 3 data.",
                "Non-UK share excludes cancellations but includes all countries.",
            ],
            suggested_follow_ups=[
                "What does the cohort retention matrix look like?",
                "What percentage of revenue goes to postage?",
            ],
        )
