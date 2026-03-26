"""
Canonical metric catalog for the Online Retail II analytics layer.

Every KPI that agents can request is registered here with its business
definition, formula, required data-quality tier, valid grains, and owning
agent.  This file is the single source of truth that bridges the design
document (docs/semantic_layer.md) and runtime analytics code.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    display_name: str
    description: str
    formula: str
    unit: str  # "GBP", "count", "ratio", "pct", "days"
    min_tier: int  # 0 = raw … 4 = customer_safe
    grain: list[str] = field(default_factory=list)
    owner_agent: str = ""
    higher_is_better: bool | None = None


# ---------------------------------------------------------------------------
# Revenue & Order KPIs
# ---------------------------------------------------------------------------

_REVENUE_ORDER: list[MetricDefinition] = [
    MetricDefinition(
        "total_gross_revenue",
        "Total Gross Revenue",
        "Sum of line revenue for positive-quantity product rows.",
        "SUM(line_revenue) WHERE quantity > 0 AND is_product",
        "GBP",
        min_tier=2,
        grain=["period", "country"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "total_net_revenue",
        "Total Net Revenue",
        "Sum of line revenue including cancellations for product rows.",
        "SUM(line_revenue) WHERE is_product",
        "GBP",
        min_tier=2,
        grain=["period", "country"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "cancellation_revenue",
        "Cancellation Value",
        "Sum of line revenue on cancellation rows (negative).",
        "SUM(line_revenue) WHERE is_cancellation AND is_product",
        "GBP",
        min_tier=2,
        grain=["period", "country"],
        owner_agent="KpiStrategy",
        higher_is_better=False,
    ),
    MetricDefinition(
        "cancellation_rate_value",
        "Cancellation Rate (Value)",
        "Absolute cancellation value as a share of gross revenue.",
        "abs(cancellation_revenue) / total_gross_revenue",
        "ratio",
        min_tier=2,
        grain=["period", "country"],
        owner_agent="KpiStrategy",
        higher_is_better=False,
    ),
    MetricDefinition(
        "cancellation_rate_count",
        "Cancellation Rate (Orders)",
        "Share of invoices that are cancellations.",
        "COUNT(DISTINCT invoice WHERE is_cancellation) / COUNT(DISTINCT invoice WHERE NOT is_cancellation)",
        "ratio",
        min_tier=2,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=False,
    ),
    MetricDefinition(
        "order_count",
        "Order Count",
        "Count of distinct non-cancellation product invoices.",
        "COUNT(DISTINCT invoice) WHERE NOT is_cancellation AND is_product",
        "count",
        min_tier=2,
        grain=["period", "country"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "avg_order_value",
        "Average Order Value",
        "Gross revenue divided by order count.",
        "total_gross_revenue / order_count",
        "GBP",
        min_tier=3,
        grain=["period", "country"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "avg_items_per_order",
        "Avg Items per Order",
        "Total units sold divided by order count.",
        "SUM(quantity WHERE qty > 0 AND is_product) / order_count",
        "count",
        min_tier=3,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=None,
    ),
    MetricDefinition(
        "avg_unit_price",
        "Average Unit Price",
        "Revenue-weighted average price per unit.",
        "SUM(line_revenue) / SUM(quantity) WHERE qty > 0 AND is_product",
        "GBP",
        min_tier=3,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=None,
    ),
    MetricDefinition(
        "revenue_per_customer",
        "Revenue per Customer",
        "Gross revenue divided by unique customer count.",
        "total_gross_revenue / COUNT(DISTINCT customer_id)",
        "GBP",
        min_tier=4,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
]

# ---------------------------------------------------------------------------
# Customer KPIs
# ---------------------------------------------------------------------------

_CUSTOMER: list[MetricDefinition] = [
    MetricDefinition(
        "unique_customers",
        "Unique Customer Count",
        "Distinct customers with at least one transaction.",
        "COUNT(DISTINCT customer_id)",
        "count",
        min_tier=4,
        grain=["period", "country"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "new_customers",
        "New Customers",
        "Customers whose first purchase falls within the period.",
        "Customers with MIN(invoice_date) in period",
        "count",
        min_tier=4,
        grain=["period"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "returning_customers",
        "Returning Customers",
        "Customers active in a prior period who also purchased in this period.",
        "Customers active before period AND active in period",
        "count",
        min_tier=4,
        grain=["period"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "customer_retention_rate",
        "Customer Retention Rate",
        "Fraction of prior-period customers who returned.",
        "returning_customers(N) / unique_customers(N-1)",
        "ratio",
        min_tier=4,
        grain=["month"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "repeat_purchase_rate",
        "Repeat Purchase Rate",
        "Share of customers with more than one order.",
        "customers with > 1 order / unique_customers",
        "ratio",
        min_tier=4,
        grain=["cumulative", "period"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "avg_orders_per_customer",
        "Avg Orders per Customer",
        "Order count divided by unique customers.",
        "order_count / unique_customers",
        "count",
        min_tier=4,
        grain=["cumulative"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "customer_lifetime_value_proxy",
        "CLV Proxy",
        "Simple CLV estimate: AOV times average orders per customer.",
        "avg_order_value * avg_orders_per_customer",
        "GBP",
        min_tier=4,
        grain=["cumulative"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "top_customers_concentration",
        "Top-N Customer Revenue Share",
        "Revenue share of top N customers.",
        "revenue of top N customers / total_gross_revenue",
        "ratio",
        min_tier=4,
        grain=["cumulative"],
        owner_agent="CustomerAnalytics",
        higher_is_better=None,
    ),
    MetricDefinition(
        "customer_country_mix",
        "Customer Country Distribution",
        "Distinct customer count by country.",
        "COUNT(DISTINCT customer_id) GROUP BY country",
        "count",
        min_tier=4,
        grain=["snapshot"],
        owner_agent="CustomerAnalytics",
        higher_is_better=None,
    ),
]

# ---------------------------------------------------------------------------
# RFM Segmentation Inputs
# ---------------------------------------------------------------------------

_RFM: list[MetricDefinition] = [
    MetricDefinition(
        "rfm_recency",
        "Recency",
        "Days since last purchase relative to a reference date.",
        "reference_date - MAX(invoice_date) per customer",
        "days",
        min_tier=4,
        grain=["customer"],
        owner_agent="CustomerAnalytics",
        higher_is_better=False,
    ),
    MetricDefinition(
        "rfm_frequency",
        "Frequency",
        "Distinct invoice count per customer.",
        "COUNT(DISTINCT invoice) per customer",
        "count",
        min_tier=4,
        grain=["customer"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "rfm_monetary",
        "Monetary",
        "Total gross revenue per customer.",
        "SUM(line_revenue WHERE qty > 0) per customer",
        "GBP",
        min_tier=4,
        grain=["customer"],
        owner_agent="CustomerAnalytics",
        higher_is_better=True,
    ),
    MetricDefinition(
        "rfm_segment",
        "RFM Segment",
        "Quintile-based customer segment label.",
        "Label from R/F/M quintile combination",
        "label",
        min_tier=4,
        grain=["customer"],
        owner_agent="CustomerAnalytics",
        higher_is_better=None,
    ),
]

# ---------------------------------------------------------------------------
# Product & Merchandising KPIs
# ---------------------------------------------------------------------------

_PRODUCT: list[MetricDefinition] = [
    MetricDefinition(
        "product_revenue",
        "Product Revenue",
        "Revenue per product (positive-quantity rows).",
        "SUM(line_revenue) WHERE qty > 0 GROUP BY stock_code",
        "GBP",
        min_tier=3,
        grain=["product", "period"],
        owner_agent="MerchandisingOps",
        higher_is_better=True,
    ),
    MetricDefinition(
        "product_units_sold",
        "Units Sold",
        "Total units sold per product.",
        "SUM(quantity) WHERE qty > 0 GROUP BY stock_code",
        "count",
        min_tier=3,
        grain=["product", "period"],
        owner_agent="MerchandisingOps",
        higher_is_better=True,
    ),
    MetricDefinition(
        "product_order_frequency",
        "Product Order Frequency",
        "How many distinct orders include this product.",
        "COUNT(DISTINCT invoice) GROUP BY stock_code",
        "count",
        min_tier=2,
        grain=["product"],
        owner_agent="MerchandisingOps",
        higher_is_better=True,
    ),
    MetricDefinition(
        "product_return_rate",
        "Product Return Rate",
        "Cancelled units as a share of units sold for each product.",
        "units_cancelled / units_sold per product",
        "ratio",
        min_tier=2,
        grain=["product"],
        owner_agent="MerchandisingOps",
        higher_is_better=False,
    ),
    MetricDefinition(
        "product_avg_price",
        "Product Avg Price",
        "Mean price per unit for each product (positive rows).",
        "AVG(price) WHERE qty > 0 GROUP BY stock_code",
        "GBP",
        min_tier=3,
        grain=["product"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
    MetricDefinition(
        "top_products_by_revenue",
        "Top Products (Revenue)",
        "Ranked list of products by total revenue.",
        "RANK BY product_revenue DESC",
        "GBP",
        min_tier=3,
        grain=["period"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
    MetricDefinition(
        "top_products_by_volume",
        "Top Products (Volume)",
        "Ranked list of products by units sold.",
        "RANK BY product_units_sold DESC",
        "count",
        min_tier=3,
        grain=["period"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
    MetricDefinition(
        "basket_size_distribution",
        "Basket Size Distribution",
        "Distribution of distinct products per invoice.",
        "HISTOGRAM OF COUNT(DISTINCT stock_code) PER invoice",
        "count",
        min_tier=2,
        grain=["period"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
    MetricDefinition(
        "country_product_heatmap",
        "Country x Product Mix",
        "Revenue by country and product combination.",
        "SUM(line_revenue) GROUP BY (country, stock_code)",
        "GBP",
        min_tier=3,
        grain=["period"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
]

# ---------------------------------------------------------------------------
# Geographic KPIs
# ---------------------------------------------------------------------------

_GEOGRAPHIC: list[MetricDefinition] = [
    MetricDefinition(
        "revenue_by_country",
        "Revenue by Country",
        "Gross revenue per country.",
        "SUM(line_revenue) WHERE qty > 0 GROUP BY country",
        "GBP",
        min_tier=3,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=None,
    ),
    MetricDefinition(
        "orders_by_country",
        "Orders by Country",
        "Order count per country.",
        "COUNT(DISTINCT invoice) GROUP BY country",
        "count",
        min_tier=2,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=None,
    ),
    MetricDefinition(
        "country_share",
        "Country Revenue Share",
        "Each country's fraction of total gross revenue.",
        "revenue_by_country / total_gross_revenue",
        "ratio",
        min_tier=3,
        grain=["period"],
        owner_agent="KpiStrategy",
        higher_is_better=None,
    ),
    MetricDefinition(
        "non_uk_revenue_share",
        "Non-UK Revenue Share",
        "Revenue from countries other than the UK as a share of total.",
        "revenue WHERE country != UK / total_gross_revenue",
        "ratio",
        min_tier=3,
        grain=["period"],
        owner_agent="FinancialInsights",
        higher_is_better=None,
    ),
]

# ---------------------------------------------------------------------------
# Time-Series / Seasonality KPIs
# ---------------------------------------------------------------------------

_TIMESERIES: list[MetricDefinition] = [
    MetricDefinition(
        "monthly_revenue",
        "Monthly Revenue",
        "Gross revenue aggregated by calendar month.",
        "SUM(line_revenue) WHERE qty > 0 GROUP BY invoice_month",
        "GBP",
        min_tier=3,
        grain=["month"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "monthly_order_count",
        "Monthly Orders",
        "Order count aggregated by calendar month.",
        "COUNT(DISTINCT invoice) GROUP BY invoice_month",
        "count",
        min_tier=2,
        grain=["month"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "dow_revenue_profile",
        "Day-of-Week Revenue",
        "Revenue distribution across weekdays.",
        "SUM(line_revenue) GROUP BY invoice_dow",
        "GBP",
        min_tier=3,
        grain=["dow"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
    MetricDefinition(
        "hourly_revenue_profile",
        "Hourly Revenue Profile",
        "Revenue distribution across hours of the day.",
        "SUM(line_revenue) GROUP BY invoice_hour",
        "GBP",
        min_tier=3,
        grain=["hour"],
        owner_agent="MerchandisingOps",
        higher_is_better=None,
    ),
    MetricDefinition(
        "mom_revenue_growth",
        "Month-over-Month Revenue Growth",
        "Percentage change in monthly revenue versus prior month.",
        "(revenue_month_N - revenue_month_N-1) / revenue_month_N-1",
        "pct",
        min_tier=3,
        grain=["month"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "yoy_revenue_growth",
        "Year-over-Year Revenue Growth",
        "Same-month comparison across calendar years.",
        "(revenue_month_N - revenue_same_month_prior_year) / prior",
        "pct",
        min_tier=3,
        grain=["month"],
        owner_agent="KpiStrategy",
        higher_is_better=True,
    ),
    MetricDefinition(
        "seasonal_index",
        "Seasonal Index",
        "Monthly revenue relative to trailing 12-month average.",
        "monthly_revenue / trailing_12m_avg",
        "ratio",
        min_tier=3,
        grain=["month"],
        owner_agent="KpiStrategy",
        higher_is_better=None,
    ),
]

# ---------------------------------------------------------------------------
# Financial / Unit Economics KPIs
# ---------------------------------------------------------------------------

_FINANCIAL: list[MetricDefinition] = [
    MetricDefinition(
        "revenue_per_invoice_line",
        "Revenue per Line Item",
        "Average revenue per invoice line.",
        "total_gross_revenue / COUNT(rows WHERE qty > 0)",
        "GBP",
        min_tier=3,
        grain=["period"],
        owner_agent="FinancialInsights",
        higher_is_better=True,
    ),
    MetricDefinition(
        "cohort_revenue",
        "Cohort Revenue",
        "Revenue attributed to customers grouped by first-purchase month.",
        "SUM(line_revenue) GROUP BY first_purchase_month, transaction_month",
        "GBP",
        min_tier=4,
        grain=["cohort", "period"],
        owner_agent="FinancialInsights",
        higher_is_better=True,
    ),
    MetricDefinition(
        "cohort_retention",
        "Cohort Retention Matrix",
        "Percentage of cohort still purchasing in subsequent months.",
        "active_in_month_N / cohort_size",
        "pct",
        min_tier=4,
        grain=["cohort", "period"],
        owner_agent="FinancialInsights",
        higher_is_better=True,
    ),
    MetricDefinition(
        "postage_as_pct_revenue",
        "Postage % of Revenue",
        "Postage and dotcom postage charges as a share of gross revenue.",
        "SUM(line_revenue WHERE stock_code IN (POST,DOT)) / total_gross_revenue",
        "pct",
        min_tier=0,
        grain=["period"],
        owner_agent="FinancialInsights",
        higher_is_better=False,
    ),
]

# ---------------------------------------------------------------------------
# Data Quality KPIs
# ---------------------------------------------------------------------------

_DATA_QUALITY: list[MetricDefinition] = [
    MetricDefinition(
        "missing_customer_pct",
        "Missing Customer ID %",
        "Share of rows with null customer_id.",
        "null_customer_rows / total_rows",
        "pct",
        min_tier=0,
        grain=["period"],
        owner_agent="DataQuality",
        higher_is_better=False,
    ),
    MetricDefinition(
        "missing_description_pct",
        "Missing Description %",
        "Share of rows with null description.",
        "null_description_rows / total_rows",
        "pct",
        min_tier=0,
        grain=["period"],
        owner_agent="DataQuality",
        higher_is_better=False,
    ),
    MetricDefinition(
        "zero_price_pct",
        "Zero Price %",
        "Share of rows where price equals zero.",
        "zero_price_rows / total_rows",
        "pct",
        min_tier=0,
        grain=["period"],
        owner_agent="DataQuality",
        higher_is_better=False,
    ),
    MetricDefinition(
        "cancellation_pct",
        "Cancellation Row %",
        "Share of rows that are cancellations.",
        "cancellation_rows / total_rows",
        "pct",
        min_tier=0,
        grain=["period"],
        owner_agent="DataQuality",
        higher_is_better=False,
    ),
    MetricDefinition(
        "non_product_pct",
        "Non-Product Row %",
        "Share of rows with non-product stock codes.",
        "non_product_rows / total_rows",
        "pct",
        min_tier=0,
        grain=["period"],
        owner_agent="DataQuality",
        higher_is_better=False,
    ),
    MetricDefinition(
        "outlier_revenue_count",
        "Outlier Revenue Row Count",
        "Number of rows where |line_revenue| exceeds threshold.",
        "COUNT(is_outlier_revenue = True)",
        "count",
        min_tier=0,
        grain=["period"],
        owner_agent="DataQuality",
        higher_is_better=False,
    ),
]

# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------


def _build_catalog() -> dict[str, MetricDefinition]:
    catalog: dict[str, MetricDefinition] = {}
    for group in (
        _REVENUE_ORDER,
        _CUSTOMER,
        _RFM,
        _PRODUCT,
        _GEOGRAPHIC,
        _TIMESERIES,
        _FINANCIAL,
        _DATA_QUALITY,
    ):
        for m in group:
            if m.metric_id in catalog:
                raise ValueError(f"Duplicate metric_id: {m.metric_id}")
            catalog[m.metric_id] = m
    return catalog


METRIC_CATALOG: dict[str, MetricDefinition] = _build_catalog()


def get_metric(metric_id: str) -> MetricDefinition:
    """Look up a metric by ID; raises KeyError if not found."""
    return METRIC_CATALOG[metric_id]


def list_metrics(*, owner_agent: str | None = None, min_tier: int | None = None) -> list[MetricDefinition]:
    """Return metrics filtered by agent and/or maximum tier."""
    result = list(METRIC_CATALOG.values())
    if owner_agent is not None:
        result = [m for m in result if m.owner_agent == owner_agent]
    if min_tier is not None:
        result = [m for m in result if m.min_tier <= min_tier]
    return result
