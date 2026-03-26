"""
Acceptance tests for the multi-agent retail analyst.

Each test maps to a sample business question defined in
``docs/validation_questions.md``.  The suite runs every question through
the full Supervisor pipeline against synthetic sample data and checks:

  - Routing (correct intent, agent selection, confidence)
  - Response structure (non-empty summary, populated data, metric citations)
  - Numeric consistency (AOV = revenue / orders, percentages in [0,1])
  - Data-quality handling (caveats present, DQ pre-check when expected)
  - Filter behaviour (period and country narrow the result)
  - Graceful fallback on unknown questions and missing specialists
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.agents.customer_insight_agent import CustomerInsightAgent
from src.agents.data_quality_agent import DataQualityAgent
from src.agents.executive_kpi_agent import ExecutiveKpiAgent
from src.agents.financial_insight_agent import FinancialInsightAgent
from src.agents.narrative_agent import NarrativeAgent
from src.agents.product_market_agent import ProductMarketAgent
from src.agents.routing import Intent, list_agent_names
from src.agents.supervisor import SupervisorAgent, SupervisorResult
from src.data.sample_data import generate_sample


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(scope="module")
def sample_df() -> pd.DataFrame:
    """Generate the synthetic dataset once per module for speed."""
    return generate_sample(n_rows=20_000, seed=42)


@pytest.fixture(scope="module")
def supervisor() -> SupervisorAgent:
    """Fully wired supervisor with all six specialists."""
    sup = SupervisorAgent()
    sup.register_specialist("KpiStrategy", ExecutiveKpiAgent())
    sup.register_specialist("CustomerAnalytics", CustomerInsightAgent())
    sup.register_specialist("MerchandisingOps", ProductMarketAgent())
    sup.register_specialist("FinancialInsights", FinancialInsightAgent())
    sup.register_specialist("DataQuality", DataQualityAgent())
    sup.register_specialist("Narrative", NarrativeAgent())
    return sup


# ===================================================================
# Helpers
# ===================================================================

_REGISTERED_AGENTS = set(list_agent_names())
_VALID_CONFIDENCES = {"high", "medium", "low"}


def _assert_cross_cutting(result: SupervisorResult) -> None:
    """Check the eight cross-cutting acceptance criteria (C1-C8)."""
    # C1: non-empty specialist responses
    assert len(result.specialist_responses) >= 1, "C1: no specialist responses"

    for resp in result.specialist_responses:
        # C2: agent name is registered
        assert resp.agent_name in _REGISTERED_AGENTS, (
            f"C2: '{resp.agent_name}' not in agent registry"
        )
        # C3: non-empty summary
        assert resp.summary and len(resp.summary.strip()) > 0, (
            f"C3: empty summary from {resp.agent_name}"
        )

    # C4: all numeric data values are finite
    for resp in result.specialist_responses:
        for key, val in resp.data.items():
            if isinstance(val, float):
                assert math.isfinite(val), f"C4: {key} is not finite ({val})"
            elif isinstance(val, dict):
                for k, v in val.items():
                    if isinstance(v, float):
                        assert math.isfinite(v), f"C4: {key}.{k} is not finite ({v})"

    # C5: DQ pre-check present when expected
    if result.route.include_data_quality:
        assert result.data_quality_response is not None, "C5: DQ pre-check missing"

    # C6: raw_data populated
    assert len(result.raw_data) >= 1, "C6: raw_data is empty"

    # C7: valid confidence
    assert result.route.confidence in _VALID_CONFIDENCES, (
        f"C7: invalid confidence '{result.route.confidence}'"
    )

    # C8: data-producing agents cite metrics
    for resp in result.specialist_responses:
        if resp.data:
            assert len(resp.metrics_used) >= 1, (
                f"C8: {resp.agent_name} has data but no metrics_used"
            )


# ===================================================================
# §1  Revenue & Executive KPIs
# ===================================================================

class TestRevenueKpis:

    def test_q1_1_total_revenue_and_orders(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q1.1: 'What is total revenue?'"""
        result = supervisor.handle(sample_df, "What is total revenue?")

        assert result.route.intent == Intent.REVENUE_OVERVIEW
        assert result.route.primary_agents == ("KpiStrategy",)

        data = result.specialist_responses[0].data
        assert "total_gross_revenue" in data
        assert "order_count" in data
        assert "avg_order_value" in data

        # consistency: AOV = revenue / orders
        expected_aov = data["total_gross_revenue"] / data["order_count"]
        assert abs(data["avg_order_value"] - expected_aov) < 0.02

        # metric citation
        assert "total_gross_revenue" in result.specialist_responses[0].metrics_used

        # DQ pre-check ran
        assert result.data_quality_response is not None

        # caveat mentions tier
        caveats_text = " ".join(result.specialist_responses[0].caveats)
        assert "tier 3" in caveats_text.lower()

        _assert_cross_cutting(result)

    def test_q1_2_revenue_period_filter(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q1.2: Period filter narrows revenue."""
        full = supervisor.handle(sample_df, "What is total revenue?")
        filtered = supervisor.handle(
            sample_df, "What is total revenue?", period="2010-12",
        )
        full_rev = full.specialist_responses[0].data["total_gross_revenue"]
        filt_rev = filtered.specialist_responses[0].data["total_gross_revenue"]

        assert filt_rev < full_rev, "Period filter did not narrow revenue"
        assert filt_rev > 0, "Filtered revenue should be positive for 2010-12"

        caveats_text = " ".join(filtered.specialist_responses[0].caveats)
        assert "2010-12" in caveats_text

        _assert_cross_cutting(filtered)

    def test_q1_3_revenue_country_filter(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q1.3: Country filter narrows revenue."""
        full = supervisor.handle(sample_df, "What is total revenue?")
        filtered = supervisor.handle(
            sample_df, "What is total revenue?", country="France",
        )
        full_rev = full.specialist_responses[0].data["total_gross_revenue"]
        filt_rev = filtered.specialist_responses[0].data["total_gross_revenue"]

        assert filt_rev < full_rev, "Country filter did not narrow revenue"
        assert filt_rev > 0, "France revenue should be positive"

        caveats_text = " ".join(filtered.specialist_responses[0].caveats)
        assert "france" in caveats_text.lower()

        _assert_cross_cutting(filtered)

    def test_q1_4_cancellation_rate(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q1.4: Cancellation rate routes to KpiStrategy."""
        result = supervisor.handle(
            sample_df, "What's the cancellation rate by value?",
        )
        assert result.route.intent == Intent.REVENUE_OVERVIEW
        assert result.route.primary_agents == ("KpiStrategy",)

        # gross revenue is tier 3 → cancellations excluded
        data = result.specialist_responses[0].data
        assert data["total_gross_revenue"] > 0
        _assert_cross_cutting(result)


# ===================================================================
# §2  Customer Analytics
# ===================================================================

class TestCustomerAnalytics:

    def test_q2_1_top_customers(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q2.1: 'Who are our top customers?'"""
        result = supervisor.handle(sample_df, "Who are our top customers?")

        assert result.route.intent == Intent.CUSTOMER_VALUE
        assert result.route.primary_agents == ("CustomerAnalytics",)

        data = result.specialist_responses[0].data
        assert "unique_customers" in data
        assert "avg_orders_per_customer" in data
        assert data["unique_customers"] > 0

        # tier 4 caveat about missing customer IDs
        caveats_text = " ".join(result.specialist_responses[0].caveats)
        assert "tier 4" in caveats_text.lower() or "customer id" in caveats_text.lower()

        _assert_cross_cutting(result)

    def test_q2_2_repeat_purchase_rate(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q2.2: Repeat purchase rate routes to CustomerAnalytics."""
        result = supervisor.handle(
            sample_df, "What is the repeat purchase rate?",
        )
        assert result.route.intent == Intent.CUSTOMER_RETENTION
        assert result.route.primary_agents == ("CustomerAnalytics",)
        _assert_cross_cutting(result)

    def test_q2_3_rfm_segments(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q2.3: RFM segmentation routes correctly and skips narrative."""
        result = supervisor.handle(sample_df, "Show me the RFM segments")

        assert result.route.intent == Intent.CUSTOMER_SEGMENTATION
        assert result.route.primary_agents == ("CustomerAnalytics",)
        assert result.route.include_narrative is False

        _assert_cross_cutting(result)


# ===================================================================
# §3  Product & Merchandising
# ===================================================================

class TestProductMerchandising:

    def test_q3_1_best_selling_products(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q3.1: 'What are the top products?'"""
        result = supervisor.handle(
            sample_df, "What are the top products?",
        )

        assert result.route.intent == Intent.PRODUCT_PERFORMANCE
        assert result.route.primary_agents == ("MerchandisingOps",)

        data = result.specialist_responses[0].data
        assert "top_products_by_revenue" in data
        assert "total_distinct_products" in data

        top = data["top_products_by_revenue"]
        assert isinstance(top, dict) and len(top) > 0
        values = list(top.values())
        assert values == sorted(values, reverse=True), "Products not sorted desc"

        assert result.data_quality_response is not None
        _assert_cross_cutting(result)

    def test_q3_2_product_returns(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q3.2: Product return rate routes to MerchandisingOps."""
        result = supervisor.handle(
            sample_df, "Which products have the highest return rate?",
        )
        assert result.route.intent == Intent.PRODUCT_RETURNS
        assert result.route.primary_agents == ("MerchandisingOps",)
        _assert_cross_cutting(result)


# ===================================================================
# §4  Geographic Analysis
# ===================================================================

class TestGeographicAnalysis:

    def test_q4_1_revenue_by_country(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q4.1: 'How is revenue split by country?'"""
        result = supervisor.handle(
            sample_df, "How is revenue split by country?",
        )
        assert result.route.intent == Intent.GEOGRAPHIC_ANALYSIS
        assert result.route.primary_agents == ("KpiStrategy",)
        _assert_cross_cutting(result)


# ===================================================================
# §5  Financial Insights
# ===================================================================

class TestFinancialInsights:

    def test_q5_1_financial_summary(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q5.1: 'Show me financial insights'"""
        result = supervisor.handle(sample_df, "Show me financial insights")

        assert result.route.intent == Intent.FINANCIAL_ANALYSIS
        assert result.route.primary_agents == ("FinancialInsights",)
        assert result.route.include_narrative is True

        data = result.specialist_responses[0].data
        assert "revenue_per_invoice_line" in data
        assert "non_uk_revenue_share" in data

        assert 0.0 <= data["non_uk_revenue_share"] <= 1.0
        assert data["revenue_per_invoice_line"] > 0

        _assert_cross_cutting(result)


# ===================================================================
# §6  Data Quality
# ===================================================================

class TestDataQuality:

    def test_q6_1_data_quality_overview(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q6.1: 'What does the data quality look like?'"""
        result = supervisor.handle(
            sample_df, "What does the data quality look like?",
        )

        assert result.route.intent == Intent.DATA_QUALITY
        assert result.route.primary_agents == ("DataQuality",)
        assert result.route.include_data_quality is False, (
            "DQ agent should not pre-check itself"
        )

        data = result.specialist_responses[0].data
        assert "missing_customer_pct" in data
        assert "cancellation_pct" in data
        assert "total_rows" in data

        assert 0.0 <= data["missing_customer_pct"] <= 1.0
        assert 0.0 <= data["cancellation_pct"] <= 1.0
        assert data["total_rows"] > 0

        _assert_cross_cutting(result)


# ===================================================================
# §7  General / Executive Overview
# ===================================================================

class TestGeneralOverview:

    def test_q7_1_executive_overview(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Q7.1: 'Give me an executive overview of the business'"""
        result = supervisor.handle(
            sample_df, "Give me an executive overview of the business",
        )

        assert result.route.intent == Intent.GENERAL_OVERVIEW
        assert result.route.confidence == "medium"
        assert result.route.include_narrative is True

        agent_names = [r.agent_name for r in result.specialist_responses]
        assert "KpiStrategy" in agent_names
        assert "CustomerAnalytics" in agent_names
        assert "MerchandisingOps" in agent_names
        assert len(agent_names) == 3

        assert result.data_quality_response is not None

        all_follow_ups: list[str] = []
        for resp in result.specialist_responses:
            all_follow_ups.extend(resp.suggested_follow_ups)
        assert len(all_follow_ups) >= 1, "No follow-up suggestions"

        _assert_cross_cutting(result)


# ===================================================================
# §8  Cross-Cutting: run every starter prompt
# ===================================================================

_STARTER_PROMPTS = [
    "Give me an executive overview of the business",
    "What is total revenue and how many orders?",
    "Who are our top customers?",
    "What are the best-selling products?",
    "How is revenue split by country?",
    "What does the data quality look like?",
    "What is the repeat purchase rate?",
    "Show me financial insights",
]


class TestStarterPrompts:
    """Every starter prompt from the Streamlit UI must pass cross-cutting checks."""

    @pytest.mark.parametrize("question", _STARTER_PROMPTS)
    def test_starter_prompt_passes_cross_cutting(
        self,
        supervisor: SupervisorAgent,
        sample_df: pd.DataFrame,
        question: str,
    ) -> None:
        result = supervisor.handle(sample_df, question)
        _assert_cross_cutting(result)


# ===================================================================
# §9  Edge Cases
# ===================================================================

class TestEdgeCases:

    def test_e1_unknown_question(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """E1: Unknown question falls back to KpiStrategy with low confidence."""
        result = supervisor.handle(sample_df, "xyzzy plugh")

        assert result.route.intent == Intent.UNKNOWN
        assert result.route.confidence == "low"
        assert result.route.primary_agents == ("KpiStrategy",)
        assert len(result.specialist_responses) >= 1
        _assert_cross_cutting(result)

    def test_e2_unregistered_specialist(
        self, sample_df: pd.DataFrame,
    ) -> None:
        """E2: Supervisor with no agents handles the question gracefully."""
        bare = SupervisorAgent()
        result = bare.handle(sample_df, "What is total revenue?")

        assert len(result.specialist_responses) >= 1
        summary = result.specialist_responses[0].summary.lower()
        assert "not registered" in summary

    def test_e3_empty_period_filter(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """E3: Nonsense period filter returns zero results without crashing."""
        result = supervisor.handle(
            sample_df, "What is total revenue?", period="9999-01",
        )

        data = result.specialist_responses[0].data
        assert data["total_gross_revenue"] == 0 or data["order_count"] == 0

    def test_e4_empty_country_filter(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """E4: Non-existent country returns zero results without crashing."""
        result = supervisor.handle(
            sample_df, "What is total revenue?", country="Atlantis",
        )

        data = result.specialist_responses[0].data
        assert data["total_gross_revenue"] == 0 or data["order_count"] == 0


# ===================================================================
# §10  Consistency: numbers agree across agents
# ===================================================================

class TestConsistency:
    """When multiple agents report overlapping metrics, they must agree."""

    def test_kpi_order_count_matches_customer_order_count(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """KPI and Customer agent order counts should differ only by tier.

        KpiStrategy uses Tier 3 (no cancellations, no zero-price).
        CustomerAnalytics uses Tier 4 (Tier 3 + known customer).
        So KPI order count >= Customer order count.
        """
        kpi_result = supervisor.handle(sample_df, "What is total revenue?")
        cust_result = supervisor.handle(sample_df, "Who are our top customers?")

        kpi_orders = kpi_result.specialist_responses[0].data["order_count"]
        cust_orders = cust_result.specialist_responses[0].data["order_count"]

        assert kpi_orders >= cust_orders, (
            f"KPI orders ({kpi_orders}) < Customer orders ({cust_orders}); "
            "Tier 3 should be a superset of Tier 4"
        )

    def test_financial_non_uk_share_is_plausible(
        self, supervisor: SupervisorAgent, sample_df: pd.DataFrame,
    ) -> None:
        """Non-UK share should be small given the dataset is ~80% UK."""
        result = supervisor.handle(sample_df, "Show me financial insights")
        share = result.specialist_responses[0].data["non_uk_revenue_share"]
        assert 0.01 < share < 0.50, (
            f"Non-UK share {share:.2%} is outside plausible range for this dataset"
        )
