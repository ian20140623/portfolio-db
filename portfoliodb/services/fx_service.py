"""Exchange rate fetching and currency conversion."""

from datetime import datetime, timedelta

import yfinance as yf

from portfoliodb.db import get_connection
from portfoliodb.utils.constants import fx_ticker, FX_CACHE_TTL_MINUTES, CURRENCIES


def fetch_rate(from_currency: str, to_currency: str) -> float:
    """Fetch exchange rate, using cache if fresh.

    Example: fetch_rate("USD", "TWD") -> 31.58
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return 1.0

    # Check cache
    cached = _get_cached_rate(from_currency, to_currency)
    if cached is not None:
        return cached

    # Fetch from Yahoo Finance
    ticker = fx_ticker(from_currency, to_currency)
    fx = yf.Ticker(ticker)
    info = fx.fast_info
    rate = info.get("lastPrice") or info.get("previousClose")
    if rate is None:
        raise ValueError(f"Could not fetch FX rate for {from_currency}/{to_currency}")

    rate = float(rate)
    _update_cache(from_currency, to_currency, rate)
    return rate


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """Convert an amount from one currency to another."""
    rate = fetch_rate(from_currency, to_currency)
    return amount * rate


def get_all_rates(base_currency: str = "TWD") -> dict[str, float]:
    """Get exchange rates from all other currencies to the base currency.

    Returns: {"USD": 31.58, "SGD": 24.92, "TWD": 1.0}
    """
    base_currency = base_currency.upper()
    rates = {}
    for curr in CURRENCIES:
        if curr == base_currency:
            rates[curr] = 1.0
        else:
            rates[curr] = fetch_rate(curr, base_currency)
    return rates


def _get_cached_rate(from_currency: str, to_currency: str) -> float | None:
    """Get cached rate if fresh enough."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM exchange_rates WHERE from_currency = ? AND to_currency = ?",
            (from_currency, to_currency),
        ).fetchone()

    if row is None:
        return None

    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.utcnow() - fetched_at > timedelta(minutes=FX_CACHE_TTL_MINUTES):
        return None

    return row["rate"]


def _update_cache(from_currency: str, to_currency: str, rate: float) -> None:
    """Insert or update cached exchange rate."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO exchange_rates (from_currency, to_currency, rate, fetched_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(from_currency, to_currency)
               DO UPDATE SET rate = ?, fetched_at = datetime('now')""",
            (from_currency, to_currency, rate, rate),
        )
