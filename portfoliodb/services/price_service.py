"""Yahoo Finance price fetching with local cache."""

import contextlib
import io
import re
import sys
from datetime import datetime, timedelta

import yfinance as yf

from portfoliodb.db import get_connection
from portfoliodb.utils.constants import PRICE_CACHE_TTL_MINUTES

# yfinance prints "no data found" / "possibly delisted" / "HTTP Error 404" to
# stderr from inside its own logger/print calls, before any exception bubbles
# up. We capture that stream around the network call so unknown tickers turn
# into a structured warning instead of polluting CLI output. Genuine errors
# (network down, library bug) still bubble — see `_replay_unexpected_stderr`.
_QUIET_STDERR_PATTERNS = (
    re.compile(r"HTTP Error 404", re.IGNORECASE),
    re.compile(r"possibly delisted", re.IGNORECASE),
    re.compile(r"no data found", re.IGNORECASE),
    re.compile(r"Quote not found", re.IGNORECASE),
)


def _is_quiet_line(line: str) -> bool:
    return any(p.search(line) for p in _QUIET_STDERR_PATTERNS)


def _replay_unexpected_stderr(captured: str) -> None:
    """Re-emit any stderr lines that are NOT known no-quote noise."""
    for line in captured.splitlines():
        if line and not _is_quiet_line(line):
            print(line, file=sys.stderr)


def fetch_price(ticker: str) -> dict:
    """Fetch the latest price for a ticker, using cache if fresh.

    Returns:
        {"ticker": str, "price": float, "currency": str, "cached": bool}

    Raises ValueError when yfinance returns no usable price; callers that
    handle multiple tickers should use `fetch_prices` instead — it converts
    the failure into a structured `warning` entry.
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

    # Capture stderr around the yfinance call so its "possibly delisted" /
    # 404 messages don't leak into normal CLI output.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        price = info.get("lastPrice") or info.get("previousClose")
    _replay_unexpected_stderr(buf.getvalue())

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

    Returns: {ticker: {"price": float, "currency": str, "cached": bool,
                       "warning": str | None}}

    Unknown / delisted tickers come back with `price=None` plus a short
    `warning` describing the data-quality issue. yfinance's own stderr noise
    is captured at fetch time and only re-emitted for lines that don't match
    known no-quote patterns — i.e. actual problems still surface.
    """
    results = {}
    for t in tickers:
        key = t.upper()
        try:
            results[key] = fetch_price(t)
        except ValueError as e:
            results[key] = {
                "ticker": key, "price": None, "currency": None,
                "warning": "no quote",
                "error": str(e),
            }
        except Exception as e:
            # Unknown failure mode — preserve the diagnostic signal rather
            # than treating it as a routine "delisted ticker" noise event.
            results[key] = {
                "ticker": key, "price": None, "currency": None,
                "warning": "fetch failed",
                "error": str(e),
            }
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
