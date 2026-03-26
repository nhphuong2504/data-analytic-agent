# Sample Business Questions & Acceptance Criteria

This document defines the representative business questions used to validate
the multi-agent retail analyst and the acceptance checks each answer must
satisfy.  Every question listed here has a corresponding executable test in
`tests/test_validation.py`.

---

## 1  Revenue & Executive KPIs

### Q1.1 — Total revenue and orders
> "What is total revenue?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `revenue_overview`, agent = `KpiStrategy` |
| Data keys | `total_gross_revenue`, `order_count`, `avg_order_value` present |
| Consistency | `avg_order_value ≈ total_gross_revenue / order_count` (±0.02) |
| Data quality | Data quality pre-check runs; caveats mention Tier 3 |
| Metric citation | `metrics_used` lists at least `total_gross_revenue` |
| Cancellation handling | Gross revenue excludes cancellation rows (Tier 3) |

### Q1.2 — Revenue with a period filter
> "What is total revenue?" (period = "2010-12")

| Check | Criterion |
|-------|-----------|
| Filter applied | Revenue differs from the unfiltered total |
| Caveat | Caveats mention the period filter |

### Q1.3 — Revenue with a country filter
> "What is total revenue?" (country = "France")

| Check | Criterion |
|-------|-----------|
| Filter applied | Only French transactions contribute |
| Caveat | Caveats mention the country filter |

### Q1.4 — Cancellation-rate question
> "What's the cancellation rate by value?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `revenue_overview`, agent = `KpiStrategy` |
| No silent inclusion | Cancellations are *not* mixed into gross revenue |

---

## 2  Customer Analytics

### Q2.1 — Top customers
> "Who are our top customers?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `customer_value`, agent = `CustomerAnalytics` |
| Data keys | `unique_customers`, `avg_orders_per_customer` present |
| Tier caveat | Caveats mention Tier 4 / missing Customer ID |

### Q2.2 — Repeat purchase rate
> "What is the repeat purchase rate?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `customer_retention`, agent = `CustomerAnalytics` |

### Q2.3 — RFM segmentation
> "Show me the RFM segments"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `customer_segmentation`, agent = `CustomerAnalytics` |
| Narrative | `include_narrative` is False (segmentation is a drill-down) |

---

## 3  Product & Merchandising

### Q3.1 — Best-selling products
> "What are the top products?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `product_performance`, agent = `MerchandisingOps` |
| Data keys | `top_products_by_revenue` (dict), `total_distinct_products` |
| Product ranking | Top-product dict is non-empty and sorted descending |
| DQ pre-check | Data quality pre-check runs |

### Q3.2 — Product return rates
> "Which products have the highest return rate?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `product_returns`, agent = `MerchandisingOps` |

---

## 4  Geographic Analysis

### Q4.1 — Revenue by country
> "How is revenue split by country?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `geographic_analysis`, agent = `KpiStrategy` |

---

## 5  Financial Insights

### Q5.1 — Financial summary
> "Show me financial insights"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `financial_analysis`, agent = `FinancialInsights` |
| Data keys | `revenue_per_invoice_line`, `non_uk_revenue_share` present |
| Range check | `non_uk_revenue_share` is between 0 and 1 |
| Narrative | `include_narrative` is True |

---

## 6  Data Quality

### Q6.1 — Data quality overview
> "What does the data quality look like?"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `data_quality`, agent = `DataQuality` |
| Data keys | `missing_customer_pct`, `cancellation_pct`, `total_rows` present |
| Range checks | Percentages between 0 and 1 |
| No double DQ | `include_data_quality` is False (this IS the DQ agent) |

---

## 7  General / Executive Overview

### Q7.1 — Executive overview
> "Give me an executive overview of the business"

| Check | Criterion |
|-------|-----------|
| Routing | Intent = `general_overview`, confidence = `medium` |
| Fan-out | Three agents respond: `KpiStrategy`, `CustomerAnalytics`, `MerchandisingOps` |
| Narrative | `include_narrative` is True |
| DQ pre-check | Data quality pre-check runs |
| Follow-ups | At least one follow-up suggestion across all responses |

---

## 8  Cross-Cutting Acceptance Criteria

These criteria apply to **every** question above:

| # | Criterion |
|---|-----------|
| C1 | `SupervisorResult.specialist_responses` is non-empty |
| C2 | Every `AgentResponse.agent_name` matches a registered agent |
| C3 | Every `AgentResponse.summary` is a non-empty string |
| C4 | Numeric data values are finite (no NaN, no Inf) |
| C5 | When `include_data_quality` is True, `data_quality_response` is not None |
| C6 | `raw_data` dict is populated with at least one key |
| C7 | Routing confidence is one of `"high"`, `"medium"`, `"low"` |
| C8 | `AgentResponse.metrics_used` is non-empty for data-producing agents |

---

## 9  Edge Cases

### E1 — Unknown question
> "xyzzy plugh"

| Check | Criterion |
|-------|-----------|
| Intent | `unknown`, confidence = `low` |
| Fallback | Routed to `KpiStrategy` as a safe default |

### E2 — Unregistered specialist
> (Supervisor with no agents registered answering "What is total revenue?")

| Check | Criterion |
|-------|-----------|
| Graceful failure | Response summary says "not registered" |

### E3 — Empty period filter
> "What is total revenue?" (period = "9999-01")

| Check | Criterion |
|-------|-----------|
| No crash | Returns a valid SupervisorResult |
| Zero data | Revenue = 0 or order count = 0 |
