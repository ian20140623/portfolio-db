"""Constants for markets, currencies, and business rules."""

# Market definitions: market code -> config
MARKETS = {
    "TW": {"currency": "TWD", "suffix": ".TW", "name": "台灣", "name_en": "Taiwan"},
    "US": {"currency": "USD", "suffix": "",    "name": "美國", "name_en": "United States"},
    "SG": {"currency": "SGD", "suffix": ".SI", "name": "新加坡", "name_en": "Singapore"},
}

CURRENCIES = {"TWD", "USD", "SGD"}

# Valid market-currency pairings
MARKET_CURRENCY = {
    "TW": "TWD",
    "US": "USD",
    "SG": "SGD",
}

# Transaction types
TRANSACTION_ACTIONS = {"BUY", "SELL"}

# Cash transaction categories
CASH_CATEGORIES = {
    "DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST", "FEE", "FX_CONVERSION",
}

# Account types
ACCOUNT_TYPES = {"brokerage", "bank"}

# Planned order statuses and priorities
ORDER_STATUSES = {"PENDING", "EXECUTED", "CANCELLED"}
ORDER_PRIORITIES = {"HIGH", "NORMAL", "LOW"}

# Tax rates
TW_SELL_TAX_RATE = 0.003  # Taiwan stock sell tax: 0.3%

# Price cache TTL in minutes
PRICE_CACHE_TTL_MINUTES = 15
FX_CACHE_TTL_MINUTES = 60

# Currency display symbols
CURRENCY_SYMBOLS = {
    "TWD": "NT$",
    "USD": "$",
    "SGD": "S$",
}

# Yahoo Finance FX ticker format: e.g. "USDTWD=X"
def fx_ticker(from_currency: str, to_currency: str) -> str:
    """Build a Yahoo Finance FX ticker like 'USDTWD=X'."""
    return f"{from_currency}{to_currency}=X"
