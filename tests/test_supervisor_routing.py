"""
Tests for the supervisor routing engine.

Covers:
  - Intent classification from natural-language questions
  - Route plan construction (agent selection, DQ inclusion, narrative flag)
  - Agent registry completeness
  - Supervisor end-to-end wiring with a synthetic DataFrame
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.agents.routing import (
    AGENT_REGISTRY,
    Intent,
    RoutePlan,
    build_route,
    classify_intent,
    get_agent_spec,
    get_agents_for_intent,
    list_agent_names,
)
from src.agents.supervisor import SupervisorAgent, SupervisorResult
from src.agents.executive_kpi_agent import ExecutiveKpiAgent
from src.agents.customer_insight_agent import CustomerInsightAgent
from src.agents.product_market_agent import ProductMarketAgent
from src.agents.financial_insight_agent import FinancialInsightAgent
from src.agents.data_quality_agent import DataQualityAgent
from src.agents.narrative_agent import NarrativeAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_df() -> pd.DataFrame:
    """Minimal DataFrame that satisfies the cleaned transaction schema."""
    return pd.DataFrame({
        "invoice": ["INV001", "INV001", "INV002", "CINV003", "INV004"],
        "stock_code": ["85123A", "71053", "84406B", "85123A", "22423"],
        "description": ["WHITE HANGING HEART", "LUNCH BAG", "CREAM CUPID", "WHITE HANGING HEART", "REGENCY CAKESTAND"],
        "quantity": [6, 6, 8, -6, 3],
        "invoice_date": pd.to_datetime([
            "2010-12-01 08:26", "2010-12-01 08:26", "2010-12-01 08:28",
            "2010-12-01 09:00", "2010-12-02 10:00",
        ]),
        "price": [2.55, 3.39, 2.75, 2.55, 10.95],
        "customer_id": pd.array([17850, 17850, 13047, pd.NA, 17850], dtype="Int64"),
        "country": ["United Kingdom", "United Kingdom", "United Kingdom", "United Kingdom", "France"],
        "line_revenue": [15.30, 20.34, 22.00, -15.30, 32.85],
        "is_cancellation": [False, False, False, True, False],
        "is_adjustment": [False, False, False, False, False],
        "is_product": [True, True, True, True, True],
        "has_customer": [True, True, True, False, True],
        "is_zero_price": [False, False, False, False, False],
        "is_negative_price": [False, False, False, False, False],
        "is_outlier_revenue": [False, False, False, False, False],
        "invoice_year": [2010, 2010, 2010, 2010, 2010],
        "invoice_month": ["2010-12", "2010-12", "2010-12", "2010-12", "2010-12"],
        "invoice_dow": [2, 2, 2, 2, 3],
        "invoice_hour": [8, 8, 8, 9, 10],
    })


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class TestClassifyIntent:
    """Verify keyword-based intent classification."""

    @pytest.mark.parametrize("question, expected", [
        ("What is total revenue?", Intent.REVENUE_OVERVIEW),
        ("Show me gross sales for this month", Intent.REVENUE_OVERVIEW),
        ("How much did we make last quarter?", Intent.REVENUE_OVERVIEW),
        ("What's the cancellation rate by value?", Intent.REVENUE_OVERVIEW),

        ("How many orders did we get?", Intent.ORDER_ANALYSIS),
        ("What is the average order value?", Intent.ORDER_ANALYSIS),
        ("AOV trend over time", Intent.ORDER_ANALYSIS),

        ("Show me the RFM segments", Intent.CUSTOMER_SEGMENTATION),
        ("What customer types do we have?", Intent.CUSTOMER_SEGMENTATION),
        ("Who are our champion customers?", Intent.CUSTOMER_SEGMENTATION),

        ("What is our customer retention rate?", Intent.CUSTOMER_RETENTION),
        ("How many repeat customers do we have?", Intent.CUSTOMER_RETENTION),
        ("Are customers coming back?", Intent.CUSTOMER_RETENTION),

        ("Who are the top customers by revenue?", Intent.CUSTOMER_VALUE),
        ("What is the customer lifetime value?", Intent.CUSTOMER_VALUE),
        ("How concentrated is revenue among top customers?", Intent.CUSTOMER_VALUE),
        ("CLV proxy?", Intent.CUSTOMER_VALUE),

        ("What are the top products?", Intent.PRODUCT_PERFORMANCE),
        ("Best selling items this month", Intent.PRODUCT_PERFORMANCE),
        ("Basket size analysis", Intent.PRODUCT_PERFORMANCE),

        ("Which products have the highest return rate?", Intent.PRODUCT_RETURNS),
        ("Most cancelled items", Intent.PRODUCT_RETURNS),

        ("Revenue by country", Intent.GEOGRAPHIC_ANALYSIS),
        ("How much comes from non-UK markets?", Intent.GEOGRAPHIC_ANALYSIS),
        ("Where are our customers located?", Intent.GEOGRAPHIC_ANALYSIS),

        ("What are the seasonal patterns?", Intent.SEASONALITY),
        ("Monthly revenue trend", Intent.SEASONALITY),
        ("Peak hour for orders", Intent.SEASONALITY),
        ("Day of week pattern", Intent.SEASONALITY),

        ("Show me the cohort retention matrix", Intent.FINANCIAL_ANALYSIS),
        ("What is revenue per line item?", Intent.FINANCIAL_ANALYSIS),
        ("How much do we spend on postage?", Intent.FINANCIAL_ANALYSIS),

        ("How much data is missing?", Intent.DATA_QUALITY),
        ("Missing customer ID percentage", Intent.DATA_QUALITY),
        ("Are there data quality issues?", Intent.DATA_QUALITY),
        ("How many outlier rows exist?", Intent.DATA_QUALITY),

        ("How is the business doing?", Intent.GENERAL_OVERVIEW),
        ("Give me a KPI dashboard", Intent.GENERAL_OVERVIEW),
        ("Executive summary please", Intent.GENERAL_OVERVIEW),
    ])
    def test_known_intents(self, question: str, expected: Intent) -> None:
        assert classify_intent(question) == expected

    def test_unknown_falls_through(self) -> None:
        assert classify_intent("xyzzy plugh") == Intent.UNKNOWN

    def test_case_insensitive(self) -> None:
        assert classify_intent("WHAT IS TOTAL REVENUE?") == Intent.REVENUE_OVERVIEW


# ---------------------------------------------------------------------------
# Route plan construction
# ---------------------------------------------------------------------------

class TestBuildRoute:

    def test_revenue_route(self) -> None:
        route = build_route("What is total revenue?")
        assert route.intent == Intent.REVENUE_OVERVIEW
        assert route.primary_agents == ("KpiStrategy",)
        assert route.include_data_quality is True
        assert route.include_narrative is True
        assert route.confidence == "high"

    def test_customer_route_no_narrative(self) -> None:
        route = build_route("Show me the RFM segments")
        assert route.intent == Intent.CUSTOMER_SEGMENTATION
        assert route.primary_agents == ("CustomerAnalytics",)
        assert route.include_narrative is False

    def test_general_overview_fans_out(self) -> None:
        route = build_route("How is the business doing?")
        assert route.intent == Intent.GENERAL_OVERVIEW
        assert len(route.primary_agents) == 3
        assert "KpiStrategy" in route.primary_agents
        assert "CustomerAnalytics" in route.primary_agents
        assert "MerchandisingOps" in route.primary_agents
        assert route.include_narrative is True
        assert route.confidence == "medium"

    def test_unknown_is_low_confidence(self) -> None:
        route = build_route("xyzzy")
        assert route.intent == Intent.UNKNOWN
        assert route.confidence == "low"
        assert route.primary_agents == ("KpiStrategy",)

    def test_data_quality_route_no_dq_precheck(self) -> None:
        route = build_route("How much data is missing?")
        assert route.intent == Intent.DATA_QUALITY
        assert route.primary_agents == ("DataQuality",)
        assert route.include_data_quality is False

    def test_product_route_includes_dq_precheck(self) -> None:
        route = build_route("What are the top products?")
        assert route.include_data_quality is True


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

class TestAgentRegistry:

    def test_all_planned_agents_registered(self) -> None:
        expected = {
            "KpiStrategy", "CustomerAnalytics", "MerchandisingOps",
            "FinancialInsights", "DataQuality", "Narrative",
        }
        assert expected == set(list_agent_names())

    def test_get_agent_spec_returns_correct_type(self) -> None:
        spec = get_agent_spec("KpiStrategy")
        assert spec.name == "KpiStrategy"
        assert spec.display_name == "Executive KPI Agent"

    def test_get_agent_spec_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_agent_spec("NonExistentAgent")

    def test_every_intent_has_agent_mapping(self) -> None:
        for intent in Intent:
            agents = get_agents_for_intent(intent)
            assert len(agents) >= 1, f"No agents mapped for {intent}"

    def test_metric_owners_match_registry(self) -> None:
        from src.tools.metric_catalog import METRIC_CATALOG
        owner_agents = {m.owner_agent for m in METRIC_CATALOG.values() if m.owner_agent}
        registered = set(list_agent_names())
        for owner in owner_agents:
            assert owner in registered, (
                f"Metric owner '{owner}' is not in the agent registry"
            )


# ---------------------------------------------------------------------------
# Supervisor end-to-end
# ---------------------------------------------------------------------------

class TestSupervisorAgent:

    def _build_supervisor(self) -> SupervisorAgent:
        sup = SupervisorAgent()
        sup.register_specialist("KpiStrategy", ExecutiveKpiAgent())
        sup.register_specialist("CustomerAnalytics", CustomerInsightAgent())
        sup.register_specialist("MerchandisingOps", ProductMarketAgent())
        sup.register_specialist("FinancialInsights", FinancialInsightAgent())
        sup.register_specialist("DataQuality", DataQualityAgent())
        sup.register_specialist("Narrative", NarrativeAgent())
        return sup

    def test_revenue_question(self, sample_df: pd.DataFrame) -> None:
        sup = self._build_supervisor()
        result = sup.handle(sample_df, "What is total revenue?")

        assert isinstance(result, SupervisorResult)
        assert result.route.intent == Intent.REVENUE_OVERVIEW
        assert len(result.specialist_responses) == 1
        assert result.specialist_responses[0].agent_name == "KpiStrategy"
        assert "total_gross_revenue" in result.specialist_responses[0].data
        assert result.data_quality_response is not None

    def test_general_overview_multiple_agents(self, sample_df: pd.DataFrame) -> None:
        sup = self._build_supervisor()
        result = sup.handle(sample_df, "How is the business doing?")

        assert result.route.intent == Intent.GENERAL_OVERVIEW
        agent_names = [r.agent_name for r in result.specialist_responses]
        assert "KpiStrategy" in agent_names
        assert "CustomerAnalytics" in agent_names
        assert "MerchandisingOps" in agent_names

    def test_missing_specialist_graceful(self, sample_df: pd.DataFrame) -> None:
        sup = SupervisorAgent()  # no specialists registered
        result = sup.handle(sample_df, "What is total revenue?")
        assert "not registered" in result.specialist_responses[0].summary.lower()

    def test_dq_precheck_runs_before_specialist(self, sample_df: pd.DataFrame) -> None:
        sup = self._build_supervisor()
        result = sup.handle(sample_df, "What is total revenue?")
        assert result.data_quality_response is not None
        assert result.data_quality_response.agent_name == "DataQuality"

    def test_period_filter_passed_through(self, sample_df: pd.DataFrame) -> None:
        sup = self._build_supervisor()
        result = sup.handle(sample_df, "What is total revenue?", period="2010-12")
        data = result.specialist_responses[0].data
        assert data["total_gross_revenue"] > 0

    def test_country_filter_passed_through(self, sample_df: pd.DataFrame) -> None:
        sup = self._build_supervisor()
        result = sup.handle(sample_df, "What is total revenue?", country="France")
        data = result.specialist_responses[0].data
        assert data["total_gross_revenue"] == 32.85
        assert data["order_count"] == 1
