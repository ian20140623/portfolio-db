"""yfinance noise capture — Sir case 6.

Asserts that:
  * No HTTPError 404 / "possibly delisted" / "no data found" line escapes to
    real stderr when a ticker has no quote.
  * The invalid ticker comes back as a structured warning rather than a print.
  * Unexpected stderr lines (anything not in the known no-quote patterns) are
    re-emitted, so we don't silently swallow real failures.
"""

from __future__ import annotations

import io

import pytest

from portfoliodb.services import price_service


class _FakeFastInfo(dict):
    """Minimal stand-in for yfinance's fast_info — supports dict.get."""


class _FakeTickerGood:
    def __init__(self, _t):
        self._t = _t

    @property
    def fast_info(self):
        return _FakeFastInfo(lastPrice=100.0, previousClose=99.0, currency="USD")


class _FakeTickerNoData:
    """Mimics yfinance: prints noise to stderr, then returns no usable price."""

    def __init__(self, _t):
        self._t = _t

    @property
    def fast_info(self):
        import sys
        print(f"HTTP Error 404: Quote not found for {self._t}", file=sys.stderr)
        print(f"${self._t}: possibly delisted; no price data found", file=sys.stderr)
        return _FakeFastInfo()  # no lastPrice / previousClose


class _FakeTickerSurprise:
    """Mimics an unexpected stderr line that is NOT a known no-quote pattern."""

    def __init__(self, _t):
        self._t = _t

    @property
    def fast_info(self):
        import sys
        print("WARNING: socket reset by peer", file=sys.stderr)
        return _FakeFastInfo(lastPrice=42.0, currency="USD")


@pytest.fixture(autouse=True)
def disable_price_cache(monkeypatch):
    monkeypatch.setattr(price_service, "_get_cached_price", lambda t: None)
    monkeypatch.setattr(price_service, "_update_cache", lambda t, p, c: None)


def test_invalid_ticker_returns_structured_warning(monkeypatch, capsys):
    monkeypatch.setattr(price_service.yf, "Ticker", _FakeTickerNoData)
    result = price_service.fetch_prices(["FAKE123"])
    assert result["FAKE123"]["price"] is None
    assert result["FAKE123"]["warning"] == "no quote"

    err = capsys.readouterr().err
    # The known no-quote noise must be swallowed.
    assert "404" not in err
    assert "possibly delisted" not in err


def test_valid_ticker_still_works(monkeypatch):
    monkeypatch.setattr(price_service.yf, "Ticker", _FakeTickerGood)
    result = price_service.fetch_prices(["AAPL"])
    assert result["AAPL"]["price"] == 100.0
    assert result["AAPL"].get("warning") is None


def test_unexpected_stderr_is_replayed_not_swallowed(monkeypatch, capsys):
    """If yfinance prints something we don't recognise, it must reach the user."""
    monkeypatch.setattr(price_service.yf, "Ticker", _FakeTickerSurprise)
    price_service.fetch_prices(["AAPL"])
    err = capsys.readouterr().err
    assert "socket reset" in err  # unknown stderr line replayed
