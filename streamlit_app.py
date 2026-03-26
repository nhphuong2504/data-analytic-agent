# -*- coding: utf-8 -*-
"""
Streamlit chat UI for the multi-agent retail analyst.

Launch with::

    streamlit run streamlit_app.py

The app loads cleaned transaction data (or generates synthetic demo data),
wires up all specialist agents through the supervisor, and exposes a chat
interface with headline KPI cards and sample starter questions.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Retail Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Project imports (after set_page_config)
# ---------------------------------------------------------------------------
from src.agents.customer_insight_agent import CustomerInsightAgent
from src.agents.data_quality_agent import DataQualityAgent
from src.agents.executive_kpi_agent import ExecutiveKpiAgent
from src.agents.financial_insight_agent import FinancialInsightAgent
from src.agents.narrative_agent import NarrativeAgent
from src.agents.product_market_agent import ProductMarketAgent
from src.agents.routing import AGENT_REGISTRY, classify_intent
from src.agents.supervisor import SupervisorAgent, SupervisorResult
from src.tools.query_tools import TIER_NAMES, apply_tier

_PROJECT_ROOT = Path(__file__).resolve().parent
_PARQUET_PATH = _PROJECT_ROOT / "data" / "processed" / "transactions_clean.parquet"


# ===================================================================
# Data loading
# ===================================================================

@st.cache_data(show_spinner="Loading data …")
def load_data() -> pd.DataFrame:
    """Load cleaned Parquet if available, otherwise generate sample data."""
    if _PARQUET_PATH.exists():
        return pd.read_parquet(_PARQUET_PATH)
    from src.data.sample_data import generate_sample
    return generate_sample()


# ===================================================================
# Agent wiring
# ===================================================================

@st.cache_resource
def build_supervisor() -> SupervisorAgent:
    """Construct and wire the supervisor + all specialist agents."""
    sup = SupervisorAgent()
    sup.register_specialist("KpiStrategy", ExecutiveKpiAgent())
    sup.register_specialist("CustomerAnalytics", CustomerInsightAgent())
    sup.register_specialist("MerchandisingOps", ProductMarketAgent())
    sup.register_specialist("FinancialInsights", FinancialInsightAgent())
    sup.register_specialist("DataQuality", DataQualityAgent())
    sup.register_specialist("Narrative", NarrativeAgent())
    return sup


# ===================================================================
# Formatting helpers
# ===================================================================

def _format_answer(result: SupervisorResult) -> str:
    """Turn a SupervisorResult into a Markdown string for the chat."""
    parts: list[str] = []

    if result.data_quality_response and result.data_quality_response.caveats:
        caveat_text = "; ".join(result.data_quality_response.caveats)
        parts.append(f"> **Data note:** {caveat_text}")

    for resp in result.specialist_responses:
        if resp.summary:
            parts.append(resp.summary)

        if resp.data:
            items = []
            for k, v in resp.data.items():
                if isinstance(v, dict):
                    continue
                if isinstance(v, float):
                    items.append(f"- **{_nice_label(k)}:** {_fmt_value(k, v)}")
                elif isinstance(v, int):
                    items.append(f"- **{_nice_label(k)}:** {v:,}")
                else:
                    items.append(f"- **{_nice_label(k)}:** {v}")
            if items:
                parts.append("\n".join(items))

        if resp.caveats:
            parts.append("_Caveats: " + "; ".join(resp.caveats) + "_")

    follow_ups: list[str] = []
    for resp in result.specialist_responses:
        follow_ups.extend(resp.suggested_follow_ups)
    unique_follow_ups = list(dict.fromkeys(follow_ups))[:3]
    if unique_follow_ups:
        suggestions = "\n".join(f"- {q}" for q in unique_follow_ups)
        parts.append(f"\n**You might also ask:**\n{suggestions}")

    routing_note = (
        f"_Route: intent=`{result.route.intent.value}`, "
        f"agents={', '.join(result.route.primary_agents)}, "
        f"confidence={result.route.confidence}_"
    )
    parts.append(routing_note)

    return "\n\n".join(parts)


def _nice_label(key: str) -> str:
    return key.replace("_", " ").title()


def _fmt_value(key: str, v: float) -> str:
    if "pct" in key or "share" in key or "rate" in key:
        return f"{v:.1%}"
    if "revenue" in key or "price" in key or "value" in key or "monetary" in key:
        return f"£{v:,.2f}"
    return f"{v:,.2f}"


# ===================================================================
# Headline KPI cards (always visible)
# ===================================================================

def _render_kpi_cards(df: pd.DataFrame) -> None:
    """Show a row of top-line KPI metric cards using Tier 3 data."""
    t3 = apply_tier(df, 3)

    gross_rev = float(t3["line_revenue"].sum())
    order_ct = int(t3["invoice"].nunique())
    aov = gross_rev / order_ct if order_ct else 0.0
    n_products = int(t3["stock_code"].nunique())

    t4 = apply_tier(df, 4)
    n_customers = int(t4["customer_id"].nunique())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Gross Revenue", f"£{gross_rev:,.0f}")
    c2.metric("Orders", f"{order_ct:,}")
    c3.metric("Avg Order Value", f"£{aov:,.2f}")
    c4.metric("Customers", f"{n_customers:,}")
    c5.metric("Products", f"{n_products:,}")


# ===================================================================
# Sidebar
# ===================================================================

def _render_sidebar(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Render sidebar filters and return (period, country) selections."""
    st.sidebar.title("🔍 Filters")

    months = sorted(df["invoice_month"].dropna().unique())
    month_options = ["All periods"] + months
    selected_month = st.sidebar.selectbox("Period (month)", month_options)
    period = None if selected_month == "All periods" else selected_month

    countries = sorted(df["country"].dropna().unique())
    country_options = ["All countries"] + countries
    selected_country = st.sidebar.selectbox("Country", country_options)
    country = None if selected_country == "All countries" else selected_country

    st.sidebar.divider()
    st.sidebar.caption(
        f"Dataset: **{len(df):,}** rows · "
        f"**{len(months)}** months · "
        f"**{len(countries)}** countries"
    )

    using_sample = not _PARQUET_PATH.exists()
    if using_sample:
        st.sidebar.info("Running on **synthetic demo data**. Place real data at "
                        "`data/raw/online_retail_II.xlsx` and re-run the cleaning "
                        "pipeline for production use.")

    st.sidebar.divider()
    st.sidebar.subheader("Agent Registry")
    for name, spec in AGENT_REGISTRY.items():
        with st.sidebar.expander(spec.display_name):
            st.caption(spec.description)

    return period, country


# ===================================================================
# Starter prompts
# ===================================================================

_STARTER_PROMPTS: list[str] = [
    "Give me an executive overview of the business",
    "What is total revenue and how many orders?",
    "Who are our top customers?",
    "What are the best-selling products?",
    "How is revenue split by country?",
    "What does the data quality look like?",
    "What is the repeat purchase rate?",
    "Show me financial insights",
]


def _render_starter_prompts() -> str | None:
    """Show clickable sample prompt buttons; return selected prompt or None."""
    st.caption("Try a question:")
    cols = st.columns(4)
    for idx, prompt in enumerate(_STARTER_PROMPTS):
        col = cols[idx % 4]
        if col.button(prompt, key=f"starter_{idx}", use_container_width=True):
            return prompt
    return None


# ===================================================================
# Main app
# ===================================================================

def main() -> None:
    df = load_data()
    supervisor = build_supervisor()
    period, country = _render_sidebar(df)

    st.title("📊 Retail Analyst")
    st.markdown(
        "Ask business questions about the online retail dataset. "
        "Answers are routed through specialist agents and backed by "
        "explicit metrics."
    )

    _render_kpi_cards(df)
    st.divider()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    starter = None
    if not st.session_state.messages:
        starter = _render_starter_prompts()

    user_input = st.chat_input("Ask a business question …")
    question = user_input or starter

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Routing to specialists …"):
                result = supervisor.handle(
                    df, question, period=period, country=country,
                )
                answer = _format_answer(result)

            st.markdown(answer)

            if result.raw_data:
                with st.expander("Raw metric data"):
                    st.json(result.raw_data)

        st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
