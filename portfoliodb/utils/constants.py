"""Constants for markets, currencies, and business rules."""

# Market definitions: market code -> config
MARKETS = {
    "TW": {"currency": "TWD", "suffix": ".TW", "name": "台灣", "name_en": "Taiwan"},
    "US": {"currency": "USD", "suffix": "",    "name": "美國", "name_en": "United States"},
    "SG": {"currency": "SGD", "suffix": ".SI", "name": "新加坡", "name_en": "Singapore"},
}

CURRENCIES = {"TWD", "USD", "SGD", "HKD", "JPY", "EUR", "CNY", "GBP", "AUD", "NZD", "ZAR"}

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

# Stock ranking methods (portfolio-db doesn't enforce a single scoring
# framework — Sir's methodology stack has three: PEG (Lynch-style, lower is
# better), Kelly f* (higher is better), and the V1 15-point model (掌握度 +
# 估值吸引力 + 長期品質, higher is better). See ../peg skill and
# scratch/20260527-投組初步想法.md (Dropbox-synced) for the source doctrine.
RANKING_METHODS = {"peg", "kelly", "fifteen_point"}
# Explicit per-method direction (not an exclusion set) so a new method added
# to RANKING_METHODS without a matching entry here fails loudly (KeyError)
# instead of silently defaulting to some direction.
RANKING_DIRECTION = {"peg": "asc", "kelly": "desc", "fifteen_point": "desc"}

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
    "HKD": "HK$",
    "JPY": "¥",
    "EUR": "€",
    "CNY": "¥",
    "GBP": "£",
    "AUD": "A$",
    "NZD": "NZ$",
    "ZAR": "R",
}

# Yahoo Finance FX ticker format: e.g. "USDTWD=X"
def fx_ticker(from_currency: str, to_currency: str) -> str:
    """Build a Yahoo Finance FX ticker like 'USDTWD=X'."""
    return f"{from_currency}{to_currency}=X"
