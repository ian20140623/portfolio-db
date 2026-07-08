"""Individual-stock ranking snapshots: PEG / Kelly f* / 15-point framework.

Sir's ranking work happens across three methodologies (see
utils/constants.RANKING_METHODS); this service just stores and retrieves
snapshots, it does not compute scores. Direction of "better" is
method-dependent (PEG: lower; Kelly/fifteen_point: higher) and is looked up
via RANKING_DIRECTION rather than hardcoded per-query.
"""

import sqlite3
from datetime import datetime

from portfoliodb.db import get_connection
from portfoliodb.models import Ranking
from portfoliodb.utils.constants import RANKING_METHODS, RANKING_DIRECTION
from portfoliodb.utils.ticker import canonical_ticker


def add_ranking(
    ticker: str,
    method: str,
    score_date: str,
    headline_score: float = None,
    weight_pct: float = None,
    source: str = None,
    notes: str = None,
    market_hint: str = None,
    method_version: str = None,
) -> Ranking:
    """Record one ranking snapshot for a ticker under a given method.

    A (ticker, method, score_date) triple is unique: a re-score on the same
    day is a correction, not a second data point. Re-running this with the
    same three keys raises rather than silently duplicating the snapshot —
    callers who really mean "I got it wrong, replace it" should inspect the
    existing row (`ticker_history()` / CLI `rank show <ticker>`) and decide
    explicitly.
    """
    method = method.lower()
    if method not in RANKING_METHODS:
        raise ValueError(f"Invalid method '{method}'. Must be one of: {', '.join(sorted(RANKING_METHODS))}")

    try:
        datetime.strptime(score_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError(f"Invalid score_date '{score_date}'. Must be YYYY-MM-DD.")

    if weight_pct is not None and not (0 <= weight_pct <= 100):
        raise ValueError(f"weight_pct must be between 0 and 100, got {weight_pct}")

    if method_version is not None:
        method_version = method_version.strip() or None

    canon, unresolved = canonical_ticker(ticker, market_hint=market_hint)
    if unresolved:
        raise ValueError(
            f"Cannot canonicalise ticker '{ticker}': {unresolved}. "
            "Please write the suffix explicitly (e.g. 2330.TW or 8299.TWO)."
        )

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO rankings
                   (ticker, method, method_version, score_date, headline_score, weight_pct, source, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (canon, method, method_version, score_date, headline_score, weight_pct, source, notes),
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                f"A {method} ranking for {canon} on {score_date} already exists. "
                "Same-day re-scores are corrections, not new data points — "
                f"run `rank show {canon}` to see the existing row."
            )
        row = conn.execute(
            "SELECT * FROM rankings WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return Ranking.from_row(row)


def list_rankings(method: str = None, ticker: str = None) -> list[Ranking]:
    """List ranking snapshots, most recent first. Optional method/ticker filters."""
    conditions = []
    params = []
    if method is not None:
        conditions.append("method = ?")
        params.append(method.lower())
    if ticker is not None:
        canon, _ = canonical_ticker(ticker)
        conditions.append("ticker = ?")
        params.append(canon)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM rankings {where} ORDER BY score_date DESC, ticker"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [Ranking.from_row(r) for r in rows]


def latest_rankings(method: str) -> list[Ranking]:
    """Most recent snapshot per ticker for a method, sorted best-to-worst.

    "Best" direction depends on the method: PEG ascends (lower = cheaper
    relative to growth), Kelly f* and the 15-point total descend.
    """
    method = method.lower()
    if method not in RANKING_METHODS:
        raise ValueError(f"Invalid method '{method}'. Must be one of: {', '.join(sorted(RANKING_METHODS))}")

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT r.* FROM rankings r
               INNER JOIN (
                   SELECT ticker, MAX(score_date) AS max_date
                   FROM rankings WHERE method = ? GROUP BY ticker
               ) latest ON r.ticker = latest.ticker AND r.score_date = latest.max_date
               WHERE r.method = ?""",
            (method, method),
        ).fetchall()

    rankings = [Ranking.from_row(r) for r in rows]
    reverse = RANKING_DIRECTION[method] == "desc"
    with_score = sorted(
        (r for r in rankings if r.headline_score is not None),
        key=lambda r: r.headline_score,
        reverse=reverse,
    )
    without_score = [r for r in rankings if r.headline_score is None]
    return with_score + without_score


def ticker_history(ticker: str) -> list[Ranking]:
    """All ranking snapshots (any method) for one ticker, oldest first."""
    canon, _ = canonical_ticker(ticker)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rankings WHERE ticker = ? ORDER BY score_date, method",
            (canon,),
        ).fetchall()
        return [Ranking.from_row(r) for r in rows]
