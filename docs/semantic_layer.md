# Semantic Layer: Cleaned Transaction Model & KPI Catalog

This document defines the data model and metric catalog that every analytics
function and agent in the project will reference.  It is the single source of
truth for "what columns mean", "how we filter", and "how each KPI is computed".

---

## 1  Raw Data Profile

| Property | Value |
|---|---|
| Source file | `data/raw/online_retail_II.xlsx` |
| Sheets | *Year 2009-2010* (525 461 rows), *Year 2010-2011* (541 910 rows) |
| Combined rows | **1 067 371** |
| Date range | 2009-12-01 to 2011-12-09 |
| Countries | 43 (United Kingdom ~92 %) |
| Unique customers | 5 942 (excluding nulls) |

### Raw columns

| Column | Raw dtype | Nulls | Notes |
|---|---|---|---|
| Invoice | object (str / int mix) | 0 | Prefix `C` = cancellation, prefix `A` = adjustment (6 rows) |
| StockCode | object | 0 | Numeric or alpha-suffixed = product; ~63 special codes (POST, DOT, M, D, etc.) |
| Description | object | 4 382 (0.41 %) | All 4 382 null-description rows also have null CustomerID |
| Quantity | int64 | 0 | Negative on cancellations (22 950 rows); no zeros |
| InvoiceDate | datetime64 | 0 | |
| Price | float64 | 0 | 6 202 zero-price rows; 5 negative-price rows |
| Customer ID | float64 | 243 007 (22.77 %) | Float because of NaN; integer IDs range 12 346 – 18 287 |
| Country | object | 0 | |

### Key data quality observations

1. **Missing Customer ID** – 22.8 % of rows.  These are unidentifiable
   transactions; they must be excluded from any customer-level metric but may
   still be included in product-level or revenue-level aggregations with a
   caveat flag.
2. **Cancellations** – 19 494 rows where `Invoice` starts with `C`.  Quantity
   is always negative.  750 cancellation rows have no Customer ID.
3. **Adjustments** – 6 rows where `Invoice` starts with `A`.  Represent
   accounting adjustments (stock code `B`, very large negative amounts).
   Should be excluded from all business metrics.
4. **Special stock codes** – POST (postage), DOT (dotcom postage), M (manual
   adjustments), D (discounts), BANK CHARGES, CRUK (charity), TEST*, gift_*,
   S (samples), PADS, ADJUST, AMAZONFEE, DCGS*, C2/C3.  These are
   non-product entries that distort product-level analysis.
5. **Zero-price rows** – 6 202 rows.  Likely samples, internal moves, or data
   errors.  Exclude from revenue metrics.
6. **Negative-price rows** – 5 rows.  Accounting corrections.  Exclude.
7. **Missing descriptions** – 4 382 rows; all also have null Customer ID.
   Likely system-generated or incomplete entries.
8. **Extreme line values** – largest positive line revenue is £168 469.60,
   largest negative is -£168 469.60 (a matching cancellation).  Second-largest
   positive £77 183.60 is also cancelled.  These are real but exceptional; the
   cleaning layer should keep them but flag them as outliers.

---

## 2  Cleaning Rules

The cleaning pipeline (`src/data/clean_online_retail.py`) will apply the
following rules **in order** and output a single Parquet file at
`data/processed/transactions_clean.parquet`.

### 2.1  Load & combine

- Read both Excel sheets and concatenate into one DataFrame.
- Reset the index.

### 2.2  Normalize types

| Column | Target dtype | Transform |
|---|---|---|
| invoice | str | Cast to string, strip whitespace |
| stock_code | str | Cast to string, strip whitespace, upper-case |
| description | str | Strip whitespace; leave NaN as-is |
| quantity | int64 | Already correct |
| invoice_date | datetime64[ns] | Already correct |
| price | float64 | Already correct |
| customer_id | Int64 (nullable int) | Cast from float; preserve NaN as `pd.NA` |
| country | str | Strip whitespace |

Column names are lowered and snake_cased from the raw names.

### 2.3  Derived columns

| New column | Type | Formula |
|---|---|---|
| `line_revenue` | float64 | `quantity * price` |
| `is_cancellation` | bool | `invoice.str.startswith("C")` |
| `is_adjustment` | bool | `invoice.str.startswith("A")` |
| `is_product` | bool | `stock_code` matches `^\d+[A-Za-z]*$` (digits, optional alpha suffix) |
| `has_customer` | bool | `customer_id.notna()` |
| `invoice_year` | int | `invoice_date.dt.year` |
| `invoice_month` | Period[M] or int | `invoice_date.dt.to_period('M')` |
| `invoice_dow` | int | `invoice_date.dt.dayofweek` (0 = Monday) |
| `invoice_hour` | int | `invoice_date.dt.hour` |

### 2.4  Row-level quality flags

| Flag column | Type | Condition |
|---|---|---|
| `is_zero_price` | bool | `price == 0` |
| `is_negative_price` | bool | `price < 0` |
| `is_outlier_revenue` | bool | `abs(line_revenue) > 10000` (configurable threshold) |

### 2.5  Exclusion tiers

Rather than deleting rows, the cleaning layer adds flags and provides named
filter presets.  Downstream code picks the appropriate tier.

| Tier | Name | Description | Excluded rows |
|---|---|---|---|
| 0 | `raw` | Everything, flags only | none |
| 1 | `no_adjustments` | Drop the 6 `A`-prefix adjustment rows | ~6 |
| 2 | `standard` | Tier 1 + drop zero-price, negative-price, non-product stock codes | ~12 000 |
| 3 | `revenue_safe` | Tier 2 + drop cancellation rows | ~31 000 |
| 4 | `customer_safe` | Tier 3 + drop rows without Customer ID | ~260 000 |

**Default for most agents: Tier 2 (`standard`).**  Cancellation handling
depends on the metric:

- Revenue metrics use Tier 3 (positive transactions only) unless the question
  specifically asks about net revenue or return rates.
- Customer metrics use Tier 4 (known customers only).
- Product-mix metrics use Tier 2 (include cancellations to see return patterns).

---

## 3  Cleaned Transaction Model

The canonical schema of `transactions_clean.parquet`:

```
TransactionRow
├── invoice            : str          PK-part   Invoice number
├── stock_code         : str          PK-part   Product identifier
├── description        : str | null             Product description
├── quantity           : int64                  Units (negative = cancellation)
├── invoice_date       : datetime64[ns]         Timestamp of transaction
├── price              : float64                Unit price in GBP
├── customer_id        : Int64 | null           Customer identifier
├── country            : str                    Shipping / billing country
├── line_revenue       : float64                quantity × price
├── is_cancellation    : bool                   Invoice starts with C
├── is_adjustment      : bool                   Invoice starts with A
├── is_product         : bool                   Stock code is a real product
├── has_customer       : bool                   Customer ID is present
├── is_zero_price      : bool                   Price == 0
├── is_negative_price  : bool                   Price < 0
├── is_outlier_revenue : bool                   |line_revenue| > threshold
├── invoice_year       : int                    Year extracted
├── invoice_month      : str                    "YYYY-MM" period string
├── invoice_dow        : int                    Day of week (0=Mon)
├── invoice_hour       : int                    Hour of day
```

Composite key: `(invoice, stock_code)` is *not* unique because the same
product can appear on the same invoice with different quantities (e.g., partial
cancellations).  The true grain is the row index.

---

## 4  KPI Catalog

Each metric definition below includes:
- **ID**: snake_case identifier used in code
- **Name**: human-readable label
- **Domain**: which agent owns it
- **Formula**: exact computation
- **Filter tier**: minimum cleaning tier required
- **Grain**: aggregation level(s) at which it is meaningful

### 4.1  Revenue & Order KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `total_gross_revenue` | Total Gross Revenue | `SUM(line_revenue) WHERE quantity > 0 AND is_product` | 2 | period, country | KpiStrategy |
| `total_net_revenue` | Total Net Revenue | `SUM(line_revenue) WHERE is_product` (includes cancellations) | 2 | period, country | KpiStrategy |
| `cancellation_revenue` | Cancellation Value | `SUM(line_revenue) WHERE is_cancellation AND is_product` | 2 | period, country | KpiStrategy |
| `cancellation_rate_value` | Cancellation Rate (by value) | `abs(cancellation_revenue) / total_gross_revenue` | 2 | period, country | KpiStrategy |
| `cancellation_rate_count` | Cancellation Rate (by orders) | `COUNT(DISTINCT invoice WHERE is_cancellation) / COUNT(DISTINCT invoice WHERE NOT is_cancellation)` | 2 | period | KpiStrategy |
| `order_count` | Order Count | `COUNT(DISTINCT invoice) WHERE NOT is_cancellation AND is_product` | 2 | period, country | KpiStrategy |
| `avg_order_value` | Average Order Value (AOV) | `total_gross_revenue / order_count` | 3 | period, country | KpiStrategy |
| `avg_items_per_order` | Avg Items per Order | `SUM(quantity WHERE qty > 0 AND is_product) / order_count` | 3 | period | KpiStrategy |
| `avg_unit_price` | Avg Unit Price | `SUM(line_revenue WHERE qty > 0 AND is_product) / SUM(quantity WHERE qty > 0 AND is_product)` | 3 | period | KpiStrategy |
| `revenue_per_customer` | Revenue per Customer | `total_gross_revenue / COUNT(DISTINCT customer_id)` | 4 | period | KpiStrategy |

### 4.2  Customer KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `unique_customers` | Unique Customer Count | `COUNT(DISTINCT customer_id)` | 4 | period, country | CustomerAnalytics |
| `new_customers` | New Customers | Customers whose first purchase falls in the period | 4 | period | CustomerAnalytics |
| `returning_customers` | Returning Customers | Customers with purchases in a prior period who also purchased in this period | 4 | period | CustomerAnalytics |
| `customer_retention_rate` | Customer Retention Rate | `returning_customers(period N) / unique_customers(period N-1)` | 4 | month | CustomerAnalytics |
| `repeat_purchase_rate` | Repeat Purchase Rate | `customers with > 1 order / unique_customers` | 4 | cumulative, period | CustomerAnalytics |
| `avg_orders_per_customer` | Avg Orders per Customer | `order_count / unique_customers` | 4 | cumulative | CustomerAnalytics |
| `customer_lifetime_value_proxy` | CLV Proxy | `avg_order_value * avg_orders_per_customer` | 4 | cumulative | CustomerAnalytics |
| `top_customers_concentration` | Top-N Customer Revenue Share | `revenue of top N customers / total_gross_revenue` | 4 | cumulative | CustomerAnalytics |
| `customer_country_mix` | Customer Country Distribution | `COUNT(DISTINCT customer_id) GROUP BY country` | 4 | snapshot | CustomerAnalytics |

### 4.3  RFM Segmentation Inputs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `rfm_recency` | Recency (days) | Days since customer's last purchase relative to reference date | 4 | customer | CustomerAnalytics |
| `rfm_frequency` | Frequency | Count of distinct invoices per customer | 4 | customer | CustomerAnalytics |
| `rfm_monetary` | Monetary | Total gross revenue per customer | 4 | customer | CustomerAnalytics |
| `rfm_segment` | RFM Segment Label | Quintile-based label (e.g., Champions, At Risk, Lost) | 4 | customer | CustomerAnalytics |

### 4.4  Product & Merchandising KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `product_revenue` | Product Revenue | `SUM(line_revenue) WHERE qty > 0 GROUP BY stock_code` | 3 | product, period | MerchandisingOps |
| `product_units_sold` | Units Sold | `SUM(quantity) WHERE qty > 0 GROUP BY stock_code` | 3 | product, period | MerchandisingOps |
| `product_order_frequency` | Product Order Frequency | `COUNT(DISTINCT invoice) GROUP BY stock_code` | 2 | product | MerchandisingOps |
| `product_return_rate` | Product Return Rate | `units_cancelled / units_sold` per product | 2 | product | MerchandisingOps |
| `product_avg_price` | Product Avg Price | `AVG(price) WHERE qty > 0 GROUP BY stock_code` | 3 | product | MerchandisingOps |
| `top_products_by_revenue` | Top-N Products (Revenue) | Ranked list | 3 | period | MerchandisingOps |
| `top_products_by_volume` | Top-N Products (Volume) | Ranked list | 3 | period | MerchandisingOps |
| `basket_size_distribution` | Basket Size Distribution | Histogram of distinct products per invoice | 2 | period | MerchandisingOps |
| `country_product_heatmap` | Country × Product Mix | Revenue by (country, stock_code) | 3 | period | MerchandisingOps |

### 4.5  Geographic KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `revenue_by_country` | Revenue by Country | `SUM(line_revenue) WHERE qty > 0 GROUP BY country` | 3 | period | KpiStrategy |
| `orders_by_country` | Orders by Country | `COUNT(DISTINCT invoice) GROUP BY country` | 2 | period | KpiStrategy |
| `country_share` | Country Revenue Share | `revenue_by_country / total_gross_revenue` | 3 | period | KpiStrategy |
| `non_uk_revenue_share` | Non-UK Revenue Share | `revenue WHERE country != 'United Kingdom' / total_gross_revenue` | 3 | period | FinancialInsights |

### 4.6  Time-Series / Seasonality KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `monthly_revenue` | Monthly Revenue | `SUM(line_revenue) WHERE qty > 0 GROUP BY invoice_month` | 3 | month | KpiStrategy |
| `monthly_order_count` | Monthly Orders | `COUNT(DISTINCT invoice) GROUP BY invoice_month` | 2 | month | KpiStrategy |
| `dow_revenue_profile` | Day-of-Week Revenue | `SUM(line_revenue) GROUP BY invoice_dow` | 3 | dow | MerchandisingOps |
| `hourly_revenue_profile` | Hourly Revenue Profile | `SUM(line_revenue) GROUP BY invoice_hour` | 3 | hour | MerchandisingOps |
| `mom_revenue_growth` | Month-over-Month Growth | `(revenue_month_N - revenue_month_N-1) / revenue_month_N-1` | 3 | month | KpiStrategy |
| `yoy_revenue_growth` | Year-over-Year Growth | Same month comparison across years | 3 | month | KpiStrategy |
| `seasonal_index` | Seasonal Index | `monthly_revenue / trailing_12m_avg` | 3 | month | KpiStrategy |

### 4.7  Financial / Unit Economics KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `revenue_per_invoice_line` | Revenue per Line Item | `total_gross_revenue / COUNT(rows WHERE qty > 0)` | 3 | period | FinancialInsights |
| `cohort_revenue` | Cohort Revenue | Revenue attributed to customers grouped by first-purchase month | 4 | cohort × period | FinancialInsights |
| `cohort_retention` | Cohort Retention Matrix | % of cohort still purchasing in month N+1, N+2, ... | 4 | cohort × period | FinancialInsights |
| `postage_as_pct_revenue` | Postage % of Revenue | `SUM(line_revenue WHERE stock_code IN ('POST','DOT')) / total_gross_revenue` | raw | period | FinancialInsights |

### 4.8  Data Quality KPIs

| ID | Name | Formula | Tier | Grain | Agent |
|---|---|---|---|---|---|
| `missing_customer_pct` | Missing Customer ID % | `rows with null customer_id / total rows` | raw | period | DataQuality |
| `missing_description_pct` | Missing Description % | `rows with null description / total rows` | raw | period | DataQuality |
| `zero_price_pct` | Zero Price % | `zero-price rows / total rows` | raw | period | DataQuality |
| `cancellation_pct` | Cancellation Row % | `cancellation rows / total rows` | raw | period | DataQuality |
| `non_product_pct` | Non-Product Row % | `non-product rows / total rows` | raw | period | DataQuality |
| `outlier_revenue_count` | Outlier Revenue Row Count | `COUNT(is_outlier_revenue = True)` | raw | period | DataQuality |

---

## 5  Metric Catalog Code Contract

`src/tools/metric_catalog.py` will expose each metric as a registry entry:

```python
@dataclass
class MetricDefinition:
    metric_id: str              # e.g. "total_gross_revenue"
    display_name: str           # e.g. "Total Gross Revenue"
    description: str            # One-sentence business meaning
    formula: str                # Human-readable formula
    unit: str                   # "GBP", "count", "ratio", "pct", "days"
    min_tier: int               # Minimum cleaning tier (0-4)
    grain: list[str]            # Valid aggregation levels
    owner_agent: str            # Which specialist agent owns this
    higher_is_better: bool | None  # Direction (None if neutral)

METRIC_CATALOG: dict[str, MetricDefinition] = { ... }
```

This catalog is the interface between agents and the analytics layer.  An agent
asks the catalog "what metrics answer question X?", then calls the
corresponding analytics function.

---

## 6  Analytics Function Signatures

Each analytics module (`kpis.py`, `customers.py`, `products.py`) will follow
this pattern:

```python
def compute_<metric_id>(
    df: pd.DataFrame,
    *,
    period: str | None = None,       # "YYYY-MM" filter
    country: str | None = None,      # Country filter
    top_n: int | None = None,        # For ranked metrics
) -> pd.DataFrame | float | dict:
    """Docstring references MetricDefinition."""
    ...
```

Filtering to the correct tier is done by a shared helper:

```python
def apply_tier(df: pd.DataFrame, tier: int) -> pd.DataFrame:
    """Filter to the requested cleaning tier."""
    ...
```

---

## 7  Special Stock Code Reference

For filtering and labeling in the merchandising agent:

| Code pattern | Meaning | Treatment |
|---|---|---|
| `POST` | Postage charges | Non-product; include in financial analysis, exclude from product metrics |
| `DOT` | Dotcom postage | Same as POST |
| `D` | Discount | Non-product |
| `M`, `m` | Manual adjustment | Non-product |
| `C2`, `C3` | Carriage charges | Non-product |
| `BANK CHARGES` | Bank charges | Non-product |
| `PADS` | Packing material | Non-product |
| `S` | Samples | Non-product |
| `CRUK` | Charity (Cancer Research UK) | Non-product |
| `TEST*` | Test entries | Non-product; exclude everywhere |
| `gift_*` | Gift vouchers | Non-product; financial analysis only |
| `ADJUST*` | Accounting adjustments | Non-product |
| `AMAZONFEE` | Amazon marketplace fees | Non-product; financial analysis only |
| `DCGS*` | Dotcom gift sets | Treat as product (they are bundled real items) |
| `SP1002` | Unknown | Non-product (3 rows) |
| `B` | Bad debt adjustment | Non-product (used only in A-prefix invoices) |

---

## 8  Country Normalization

The dataset contains 43 distinct country strings.  Known issues:

- `EIRE` should map to `Ireland` for consistent reporting.
- `RSA` should map to `South Africa`.
- `Channel Islands` and `European Community` and `Unspecified` are ambiguous
  groupings that should be preserved but flagged.

A mapping dict in `clean_online_retail.py` will standardize names.

---

## 9  Date Grain Conventions

| Grain | Format | Example |
|---|---|---|
| Day | `YYYY-MM-DD` | `2010-03-15` |
| Week | ISO week `YYYY-WNN` | `2010-W11` |
| Month | `YYYY-MM` | `2010-03` |
| Quarter | `YYYY-QN` | `2010-Q1` |
| Year | `YYYY` | `2010` |

The default reporting grain is **month**.  Agents may request finer grains.

---

## 10  Implementation Files

| File | Purpose |
|---|---|
| `src/data/load_online_retail.py` | Read both Excel sheets, concatenate, return raw DataFrame |
| `src/data/clean_online_retail.py` | Apply cleaning rules (Section 2), write Parquet |
| `src/analytics/kpis.py` | Revenue, order, geographic, and time-series KPI functions |
| `src/analytics/customers.py` | Customer, RFM, cohort, retention functions |
| `src/analytics/products.py` | Product performance, basket, and return-rate functions |
| `src/tools/metric_catalog.py` | MetricDefinition registry (Section 5) |
| `src/tools/query_tools.py` | Shared helpers: `apply_tier`, period filters, ranking |
| `tests/test_clean_online_retail.py` | Cleaning pipeline tests |
| `tests/test_kpis.py` | KPI computation tests |
| `tests/test_customers.py` | Customer metric tests |
| `tests/test_products.py` | Product metric tests |
