"""
Supervisor routing engine for the multi-agent retail analyst.

Provides intent classification (keyword-based for v1), an agent registry
that maps specialist names to their responsibilities, and routing rules
that translate classified intents into ordered agent execution plans.

The routing layer is intentionally decoupled from LLM calls so it can be
tested deterministically and swapped to an LLM-based classifier later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, unique


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

@unique
class Intent(Enum):
    """Business-question intents recognised by the supervisor."""

    REVENUE_OVERVIEW = "revenue_overview"
    ORDER_ANALYSIS = "order_analysis"
    CUSTOMER_SEGMENTATION = "customer_segmentation"
    CUSTOMER_RETENTION = "customer_retention"
    CUSTOMER_VALUE = "customer_value"
    PRODUCT_PERFORMANCE = "product_performance"
    PRODUCT_RETURNS = "product_returns"
    GEOGRAPHIC_ANALYSIS = "geographic_analysis"
    SEASONALITY = "seasonality"
    FINANCIAL_ANALYSIS = "financial_analysis"
    DATA_QUALITY = "data_quality"
    GENERAL_OVERVIEW = "general_overview"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Keyword rules for v1 intent classification
# ---------------------------------------------------------------------------
# Each rule is (compiled regex pattern, intent).  Patterns are tried in order;
# the first match wins.  Patterns are case-insensitive.

_INTENT_PATTERNS: list[tuple[re.Pattern[str], Intent]] = [
    # --- data quality (check early so explicit DQ questions aren't swallowed) ---
    (re.compile(
        r"data\s*quality|missing\s*(customer|id|data)|data\b.*\bmissing|"
        r"\bnull\b|outlier|"
        r"zero[\s-]?price|negative[\s-]?price|adjustment\s*row|"
        r"data\s*health|data\s*issue|data\s*clean",
        re.IGNORECASE,
    ), Intent.DATA_QUALITY),

    # --- financial / cohort / unit economics (before retention so "cohort
    #     retention" is captured here rather than in customer retention) ---
    (re.compile(
        r"cohort|unit\s*economic|postage|revenue\s*per\s*line|"
        r"financial\s*(insight|analysis|summary)|margin|"
        r"cost\s*structure",
        re.IGNORECASE,
    ), Intent.FINANCIAL_ANALYSIS),

    # --- customer segmentation / RFM ---
    (re.compile(
        r"rfm|segment|cluster|champion|at[\s-]?risk|loyal|"
        r"customer\s*(type|group|categor|tier|class)",
        re.IGNORECASE,
    ), Intent.CUSTOMER_SEGMENTATION),

    # --- customer retention ---
    (re.compile(
        r"retention|churn|repeat\s*(purchase|customer)|return(ing)?\s*customer|"
        r"repurchase|lapsed|win[\s-]?back|com(e|ing)\s*back",
        re.IGNORECASE,
    ), Intent.CUSTOMER_RETENTION),

    # --- customer value ---
    (re.compile(
        r"clv|lifetime\s*value|top\s*customer|customer\s*concentration|"
        r"best\s*customer|vip|whale|high[\s-]?value\s*customer|"
        r"customer\s*revenue\s*share|revenue\s*per\s*customer",
        re.IGNORECASE,
    ), Intent.CUSTOMER_VALUE),

    # --- product returns / cancellations at the product level ---
    (re.compile(
        r"(product|item|sku)\s*(return|cancel|refund)|"
        r"return\s*rate|cancel.*product|most\s*(returned|cancelled)",
        re.IGNORECASE,
    ), Intent.PRODUCT_RETURNS),

    # --- product performance ---
    (re.compile(
        r"(top|best|worst|popular)\s*\w*\s*(product|item|sku)|"
        r"(best|top)\s*sell|"
        r"product\s*(revenue|performance|sales|rank)|"
        r"basket\s*(size|analysis)|merchandise|units\s*sold|"
        r"product\s*mix|cross[\s-]?sell",
        re.IGNORECASE,
    ), Intent.PRODUCT_PERFORMANCE),

    # --- geographic ---
    (re.compile(
        r"country|countries|geographic|region|international|"
        r"uk\s*vs|non[\s-]?uk|domestic|export|market\s*(mix|share)|"
        r"where\s*(do|are)\s*\w*\s*(we|customer|order|locate)",
        re.IGNORECASE,
    ), Intent.GEOGRAPHIC_ANALYSIS),

    # --- order analysis (before seasonality so "AOV trend" is captured here) ---
    (re.compile(
        r"order\s*(count|volume|size)|aov|average\s*order|"
        r"items\s*per\s*order|how\s*many\s*order|"
        r"order\s*(trend|growth|decline)",
        re.IGNORECASE,
    ), Intent.ORDER_ANALYSIS),

    # --- seasonality / time patterns ---
    (re.compile(
        r"season|monthly\s*trend|day[\s-]?of[\s-]?week|hourly|"
        r"peak\s*(time|hour|day|month)|holiday|christmas|"
        r"when\s*(do|is|are)|time\s*pattern|mom\s*growth|"
        r"year[\s-]?over[\s-]?year|yoy|trend",
        re.IGNORECASE,
    ), Intent.SEASONALITY),

    # --- revenue (broad) ---
    (re.compile(
        r"revenue|sales|income|gross|net\s*revenue|"
        r"cancel.*rate|cancel.*value|how\s*much\s*(did|do|are)\s*we",
        re.IGNORECASE,
    ), Intent.REVENUE_OVERVIEW),

    # --- general overview ---
    (re.compile(
        r"overview|summary|dashboard|kpi|health|"
        r"how\s*(is|was|are)\s*(the\s*)?(business|company|store)|"
        r"executive\s*summary|snapshot|big\s*picture|"
        r"tell\s*me\s*about|overall",
        re.IGNORECASE,
    ), Intent.GENERAL_OVERVIEW),
]


def classify_intent(question: str) -> Intent:
    """Return the first matching intent for *question*, or UNKNOWN."""
    for pattern, intent in _INTENT_PATTERNS:
        if pattern.search(question):
            return intent
    return Intent.UNKNOWN


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Declarative specification for one specialist agent."""

    name: str
    display_name: str
    description: str
    owned_metric_prefix: str  # matches MetricDefinition.owner_agent
    system_prompt: str
    handles_intents: frozenset[Intent] = field(default_factory=frozenset)
    needs_data_quality_precheck: bool = True
    default_tier: int = 2


AGENT_REGISTRY: dict[str, AgentSpec] = {}


def _register(spec: AgentSpec) -> AgentSpec:
    AGENT_REGISTRY[spec.name] = spec
    return spec


# ---- KpiStrategy -----------------------------------------------------------
KPI_STRATEGY = _register(AgentSpec(
    name="KpiStrategy",
    display_name="Executive KPI Agent",
    description=(
        "Owns revenue, order volume, geographic distribution, and time-series "
        "trend metrics. Answers executive-level 'how is the business doing' "
        "questions with precise, metric-backed summaries."
    ),
    owned_metric_prefix="KpiStrategy",
    system_prompt=(
        "You are the Executive KPI analyst for an online retail business. "
        "Answer questions about total revenue, order counts, average order "
        "value, country revenue mix, month-over-month growth, and seasonal "
        "patterns. Always cite the specific metric ID and the data tier used. "
        "If the question involves customer-level breakdowns, defer to "
        "CustomerAnalytics. If it involves product rankings, defer to "
        "MerchandisingOps."
    ),
    handles_intents=frozenset({
        Intent.REVENUE_OVERVIEW,
        Intent.ORDER_ANALYSIS,
        Intent.GEOGRAPHIC_ANALYSIS,
        Intent.SEASONALITY,
        Intent.GENERAL_OVERVIEW,
    }),
    default_tier=3,
))

# ---- CustomerAnalytics -----------------------------------------------------
CUSTOMER_ANALYTICS = _register(AgentSpec(
    name="CustomerAnalytics",
    display_name="Customer Insight Agent",
    description=(
        "Owns customer counts, segmentation (RFM), retention, repeat-purchase "
        "rates, CLV proxies, and customer concentration analysis. All metrics "
        "require Tier 4 (customer_safe) data."
    ),
    owned_metric_prefix="CustomerAnalytics",
    system_prompt=(
        "You are the Customer Analytics specialist for an online retail "
        "business. Answer questions about customer segments, retention, "
        "repeat-purchase behaviour, RFM analysis, lifetime value, and "
        "top-customer concentration. Always note that your metrics require "
        "Tier 4 data (known customers only, ~77% of rows). Quantify the "
        "coverage gap when relevant."
    ),
    handles_intents=frozenset({
        Intent.CUSTOMER_SEGMENTATION,
        Intent.CUSTOMER_RETENTION,
        Intent.CUSTOMER_VALUE,
    }),
    default_tier=4,
))

# ---- MerchandisingOps ------------------------------------------------------
MERCHANDISING_OPS = _register(AgentSpec(
    name="MerchandisingOps",
    display_name="Product & Merchandising Agent",
    description=(
        "Owns product performance rankings, return rates, basket analysis, "
        "day-of-week and hourly profiles, and country-product cross-tabs. "
        "Identifies operational patterns and anomalies in the product mix."
    ),
    owned_metric_prefix="MerchandisingOps",
    system_prompt=(
        "You are the Merchandising & Operations analyst for an online retail "
        "business. Answer questions about top products (by revenue or volume), "
        "product return rates, basket composition, day-of-week patterns, and "
        "hourly profiles. Use Tier 2 data when analysing return patterns and "
        "Tier 3 for positive-sales rankings. Flag products with unusually "
        "high return rates."
    ),
    handles_intents=frozenset({
        Intent.PRODUCT_PERFORMANCE,
        Intent.PRODUCT_RETURNS,
    }),
    default_tier=3,
))

# ---- FinancialInsights -----------------------------------------------------
FINANCIAL_INSIGHTS = _register(AgentSpec(
    name="FinancialInsights",
    display_name="Financial Insights Agent",
    description=(
        "Owns cohort-based revenue and retention analysis, unit economics "
        "(revenue per line), postage cost ratios, and non-UK revenue share. "
        "Provides deeper financial diagnostics beyond headline KPIs."
    ),
    owned_metric_prefix="FinancialInsights",
    system_prompt=(
        "You are the Financial Insights analyst for an online retail business. "
        "Answer questions about cohort revenue, cohort retention matrices, "
        "revenue per invoice line, postage as a percentage of revenue, and "
        "non-UK revenue share. When discussing cohort analysis, always state "
        "the cohort definition (first-purchase month) and the data tier used."
    ),
    handles_intents=frozenset({
        Intent.FINANCIAL_ANALYSIS,
    }),
    default_tier=4,
))

# ---- DataQuality -----------------------------------------------------------
DATA_QUALITY = _register(AgentSpec(
    name="DataQuality",
    display_name="Data Quality Agent",
    description=(
        "Owns data completeness and quality metrics: missing customer IDs, "
        "missing descriptions, zero-price rows, cancellation percentages, "
        "non-product rows, and outlier revenue counts. Called as a pre-check "
        "before other specialists when data caveats might affect the answer."
    ),
    owned_metric_prefix="DataQuality",
    system_prompt=(
        "You are the Data Quality guardian for an online retail dataset. "
        "Report on missing customer IDs (~23%), zero-price rows, negative "
        "prices, cancellation volume, non-product stock codes, and outlier "
        "revenue rows. When asked by the supervisor, produce a brief data "
        "quality caveat that other agents can prepend to their answers. "
        "Use Tier 0 (raw) data for all quality checks."
    ),
    handles_intents=frozenset({
        Intent.DATA_QUALITY,
    }),
    needs_data_quality_precheck=False,  # it IS the quality agent
    default_tier=0,
))

# ---- Narrative (Storytelling) ----------------------------------------------
NARRATIVE = _register(AgentSpec(
    name="Narrative",
    display_name="Storytelling Agent",
    description=(
        "Translates metric-backed outputs from other specialists into "
        "executive-ready business narratives with implications, caveats, "
        "and suggested follow-up questions."
    ),
    owned_metric_prefix="",  # does not own metrics directly
    system_prompt=(
        "You are a data storytelling specialist. Take the structured metric "
        "output provided by other agents and rewrite it as a clear, concise "
        "executive summary. Highlight the most important insight first, add "
        "business implications, note any data caveats, and suggest 2-3 "
        "follow-up questions the user might want to explore."
    ),
    handles_intents=frozenset(),  # never directly routed to
    needs_data_quality_precheck=False,
    default_tier=0,
))


# ---------------------------------------------------------------------------
# Routing rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RoutePlan:
    """An ordered execution plan produced by the router."""

    intent: Intent
    primary_agents: tuple[str, ...]
    include_data_quality: bool
    include_narrative: bool
    confidence: str  # "high", "medium", "low"


# Maps each intent to its primary agent sequence.  For GENERAL_OVERVIEW the
# supervisor fans out to multiple specialists and aggregates.
_INTENT_TO_AGENTS: dict[Intent, tuple[str, ...]] = {
    Intent.REVENUE_OVERVIEW:        ("KpiStrategy",),
    Intent.ORDER_ANALYSIS:          ("KpiStrategy",),
    Intent.CUSTOMER_SEGMENTATION:   ("CustomerAnalytics",),
    Intent.CUSTOMER_RETENTION:      ("CustomerAnalytics",),
    Intent.CUSTOMER_VALUE:          ("CustomerAnalytics",),
    Intent.PRODUCT_PERFORMANCE:     ("MerchandisingOps",),
    Intent.PRODUCT_RETURNS:         ("MerchandisingOps",),
    Intent.GEOGRAPHIC_ANALYSIS:     ("KpiStrategy",),
    Intent.SEASONALITY:             ("KpiStrategy",),
    Intent.FINANCIAL_ANALYSIS:      ("FinancialInsights",),
    Intent.DATA_QUALITY:            ("DataQuality",),
    Intent.GENERAL_OVERVIEW:        ("KpiStrategy", "CustomerAnalytics", "MerchandisingOps"),
    Intent.UNKNOWN:                 ("KpiStrategy",),
}

# Intents that always produce a narrative wrapper for the final answer.
_NARRATIVE_INTENTS: frozenset[Intent] = frozenset({
    Intent.GENERAL_OVERVIEW,
    Intent.REVENUE_OVERVIEW,
    Intent.FINANCIAL_ANALYSIS,
})


def build_route(question: str) -> RoutePlan:
    """Classify *question* and return a full routing plan."""
    intent = classify_intent(question)
    agents = _INTENT_TO_AGENTS[intent]

    any_needs_dq = any(
        AGENT_REGISTRY[a].needs_data_quality_precheck for a in agents
    )

    confidence: str
    if intent is Intent.UNKNOWN:
        confidence = "low"
    elif intent is Intent.GENERAL_OVERVIEW:
        confidence = "medium"
    else:
        confidence = "high"

    return RoutePlan(
        intent=intent,
        primary_agents=agents,
        include_data_quality=any_needs_dq,
        include_narrative=intent in _NARRATIVE_INTENTS,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def get_agents_for_intent(intent: Intent) -> tuple[str, ...]:
    """Return the primary agent name(s) for the given intent."""
    return _INTENT_TO_AGENTS.get(intent, ("KpiStrategy",))


def get_agent_spec(name: str) -> AgentSpec:
    """Look up an agent spec by name; raises KeyError if not found."""
    return AGENT_REGISTRY[name]


def list_agent_names() -> list[str]:
    """Return all registered agent names."""
    return list(AGENT_REGISTRY.keys())
