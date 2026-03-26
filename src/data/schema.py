"""
Cleaned transaction model schema definition.

Defines the canonical column set, types, and derived-column contracts for
``data/processed/transactions_clean.parquet``.  Used by the cleaning pipeline
and by tests to verify output shape.
"""

from __future__ import annotations

CLEAN_COLUMNS: dict[str, str] = {
    # --- carried from raw ---
    "invoice": "str",
    "stock_code": "str",
    "description": "str (nullable)",
    "quantity": "int64",
    "invoice_date": "datetime64[ns]",
    "price": "float64",
    "customer_id": "Int64 (nullable)",
    "country": "str",
    # --- derived ---
    "line_revenue": "float64",
    "is_cancellation": "bool",
    "is_adjustment": "bool",
    "is_product": "bool",
    "has_customer": "bool",
    "is_zero_price": "bool",
    "is_negative_price": "bool",
    "is_outlier_revenue": "bool",
    "invoice_year": "int",
    "invoice_month": "str",
    "invoice_dow": "int",
    "invoice_hour": "int",
}

EXPECTED_COLUMN_NAMES: list[str] = list(CLEAN_COLUMNS.keys())

RAW_TO_CLEAN_RENAME: dict[str, str] = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "price",
    "Customer ID": "customer_id",
    "Country": "country",
}

OUTLIER_REVENUE_THRESHOLD: float = 10_000.0

COUNTRY_NORMALIZATION: dict[str, str] = {
    "EIRE": "Ireland",
    "RSA": "South Africa",
}

SPECIAL_STOCK_CODES: set[str] = {
    "POST",
    "DOT",
    "D",
    "M",
    "C2",
    "C3",
    "BANK CHARGES",
    "PADS",
    "S",
    "CRUK",
    "GIFT",
    "ADJUST",
    "ADJUST2",
    "AMAZONFEE",
    "B",
    "SP1002",
}

SPECIAL_STOCK_PREFIXES: tuple[str, ...] = (
    "TEST",
    "gift_",
)

NON_PRODUCT_PATTERN: str = (
    r"^(POST|DOT|D|M|m|C2|C3|BANK CHARGES|PADS|S|CRUK|GIFT|"
    r"ADJUST\d*|AMAZONFEE|B|SP1002|TEST\d*|gift_\d+_\d+)$"
)

PRODUCT_PATTERN: str = r"^\d+[A-Za-z]*$"
