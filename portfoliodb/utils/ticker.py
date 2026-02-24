"""Ticker validation, normalization, and market detection."""

from portfoliodb.utils.constants import MARKETS


def detect_market(ticker: str) -> str:
    """Detect market from ticker suffix.

    Examples:
        "2330.TW" -> "TW"
        "AAPL"    -> "US"
        "D05.SI"  -> "SG"
    """
    ticker = ticker.upper()
    if ticker.endswith(".TW"):
        return "TW"
    elif ticker.endswith(".SI"):
        return "SG"
    else:
        return "US"


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker to uppercase."""
    return ticker.upper().strip()


def validate_ticker(ticker: str) -> bool:
    """Basic validation: non-empty, no spaces."""
    ticker = ticker.strip()
    if not ticker or " " in ticker:
        return False
    return True


def get_market_name(market: str) -> str:
    """Get display name for a market code."""
    info = MARKETS.get(market.upper())
    return info["name"] if info else market
