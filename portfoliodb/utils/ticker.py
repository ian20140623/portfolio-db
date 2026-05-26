"""Ticker validation, normalization, and market detection.

Two-layer identity model (since 2026-05-26):
  * canonical ticker = instrument-layer key (e.g. "2330.TW", "TSM").
    Single source of truth, written into all DB ticker columns.
  * company_id      = issuer-layer key (e.g. "TSMC"), resolved via the
    `instruments` reference table. TSM and 2330.TW share company_id "TSMC"
    but remain separate instruments (ADR vs common share, different market /
    currency / price / P&L).

`canonical_ticker()` is the only place where suffix normalization lives.
All write-path entries (order add, holding add, tx buy, sync, imports)
must route through it; do not duplicate the rules elsewhere.
"""

from portfoliodb.utils.constants import MARKETS


def detect_market(ticker: str) -> str:
    """Detect market from ticker suffix.

    .TW = 上市, .TWO = 上櫃 — both map to TW market (TWD).

    Examples:
        "2330.TW"  -> "TW"
        "8299.TWO" -> "TW"
        "AAPL"     -> "US"
        "D05.SI"   -> "SG"
    """
    ticker = ticker.upper()
    if ticker.endswith(".TW") or ticker.endswith(".TWO"):
        return "TW"
    elif ticker.endswith(".SI"):
        return "SG"
    else:
        return "US"


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker to uppercase (legacy helper, kept for compatibility).

    For full canonicalisation including suffix inference, use `canonical_ticker`.
    """
    return ticker.upper().strip()


def canonical_ticker(raw: str, market_hint: str | None = None) -> tuple[str, str | None]:
    """Return the canonical ticker plus optional unresolved reason.

    Rules:
      1. Already-suffixed tickers (`.TW` / `.TWO` / `.SI`) are returned as-is.
      2. Pure-letter ticker with no dot -> treated as US, returned as-is.
      3. Pure-digit ticker:
         - market_hint == "TW" and starts with "2" or "3" (上市 only, no ambiguity)
           -> append ".TW".
         - market_hint == "TW" but starts with "6" / "8" / "9" (could be 上市
           or 上櫃) -> returned unchanged with an `unresolved` reason; caller
           must put it on a manual-review list rather than guess a suffix.
         - market_hint is None or non-TW -> returned unchanged with `unresolved`
           reason (we refuse to guess without explicit market context).
      4. Mixed letters+digits with no recognised suffix -> returned as-is
         (US is the default, e.g. BRK.B kept verbatim).

    Returns (canonical, unresolved_reason). `unresolved_reason` is None when
    the canonical form is trusted; otherwise it's a short human-readable string.
    """
    if raw is None:
        raise ValueError("ticker is None")
    t = raw.upper().strip()
    if not t:
        raise ValueError("ticker is empty")

    if "." in t:
        return t, None

    if t.isalpha():
        return t, None

    if t.isdigit():
        hint = (market_hint or "").upper() or None
        if hint == "TW":
            if t[0] in ("2", "3"):
                return f"{t}.TW", None
            if t[0] in ("6", "8", "9"):
                return t, f"TW digit ticker starting with {t[0]} could be .TW or .TWO — needs manual confirmation"
            return t, f"unrecognised TW digit prefix {t[0]}"
        return t, "digit-only ticker with no TW market hint"

    return t, None


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


def resolve_instrument(ticker: str) -> dict | None:
    """Look up the instruments row for a canonical ticker, or return None.

    The `instruments` table is the bridge from canonical ticker string to
    instrument_id and (optionally) company_id. Callers should treat absence
    as "instrument not yet registered" rather than an error — registration
    is lazy and happens via the 001 migration / future broker imports.
    """
    from portfoliodb.db import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT instrument_id, ticker, market, currency, company_id, "
            "       security_type, notes "
            "FROM instruments WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        return dict(row) if row else None


def resolve_company(ticker: str) -> dict | None:
    """Look up the company row for a canonical ticker via instruments, or None.

    Returns the companies row when the instrument is linked to a company.
    Used by issuer-level aggregation; intentionally not called from order /
    position / P&L code paths.
    """
    from portfoliodb.db import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT c.company_id, c.display_name, c.notes "
            "FROM instruments i JOIN companies c ON i.company_id = c.company_id "
            "WHERE i.ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        return dict(row) if row else None
