"""Yahoo Finance price fetching with local cache."""

from datetime import datetime, timedelta

import yfinance as yf

from portfoliodb.db import get_connection
from portfoliodb.utils.constants import PRICE_CACHE_TTL_MINUTES


def fetch_price(ticker: str) -> dict:
    """Fetch the latest price for a ticker, using cache if fresh.

    Returns:
        {"ticker": str, "price": float, "currency": str, "cached": bool}
    """
    ticker = ticker.upper()

    # Check cache first
    cached = _get_cached_price(ticker)
    if cached:
        return {
            "ticker": ticker,
            "price": cached["price"],
            "currency": cached["currency"],
            "cached": True,
        }

    # Fetch from Yahoo Finance
    stock = yf.Ticker(ticker)
    info = stock.fast_info
    price = info.get("lastPrice") or info.get("previousClose")
    if price is None:
        raise ValueError(f"Could not fetch price for {ticker}")

    price = float(price)
    currency = str(info.get("currency", "USD"))

    # Update cache
    _update_cache(ticker, price, currency)

    return {
        "ticker": ticker,
        "price": price,
        "currency": currency,
        "cached": False,
    }


def fetch_prices(tickers: list[str]) -> dict[str, dict]:
    """Fetch prices for multiple tickers.

    Returns: {ticker: {"price": float, "currency": str, "cached": bool}}
    """
    results = {}
    for t in tickers:
        try:
            results[t.upper()] = fetch_price(t)
        except Exception as e:
            results[t.upper()] = {"ticker": t.upper(), "price": None, "currency": None, "error": str(e)}
    return results


def _get_cached_price(ticker: str) -> dict | None:
    """Get cached price if it's fresh enough."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM price_cache WHERE ticker = ?", (ticker,)
        ).fetchone()

    if row is None:
        return None

    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.utcnow() - fetched_at > timedelta(minutes=PRICE_CACHE_TTL_MINUTES):
        return None  # Cache expired

    return {"price": row["price"], "currency": row["currency"]}


def _update_cache(ticker: str, price: float, currency: str) -> None:
    """Insert or update the price cache."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO price_cache (ticker, price, currency, fetched_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(ticker)
               DO UPDATE SET price = ?, currency = ?, fetched_at = datetime('now')""",
            (ticker, price, currency, price, currency),
        )
