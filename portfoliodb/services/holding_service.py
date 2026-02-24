"""Holdings management: track stock positions per account."""

from portfoliodb.db import get_connection
from portfoliodb.models import Holding


def add_holding(account_id: int, ticker: str, shares: float, avg_cost: float) -> Holding:
    """Add or import a holding manually (e.g. initial portfolio setup).

    If the ticker already exists in this account, updates shares and avg_cost.
    """
    ticker = ticker.upper()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM holdings WHERE account_id = ? AND ticker = ?",
            (account_id, ticker),
        ).fetchone()

        if existing:
            # Merge: recalculate weighted average cost
            old_shares = existing["shares"]
            old_cost = existing["avg_cost"]
            new_total_shares = old_shares + shares
            if new_total_shares > 0:
                new_avg_cost = (
                    (old_shares * old_cost) + (shares * avg_cost)
                ) / new_total_shares
            else:
                new_avg_cost = 0

            conn.execute(
                """UPDATE holdings
                   SET shares = ?, avg_cost = ?, updated_at = datetime('now')
                   WHERE account_id = ? AND ticker = ?""",
                (new_total_shares, new_avg_cost, account_id, ticker),
            )
        else:
            conn.execute(
                """INSERT INTO holdings (account_id, ticker, shares, avg_cost)
                   VALUES (?, ?, ?, ?)""",
                (account_id, ticker, shares, avg_cost),
            )

        row = conn.execute(
            "SELECT * FROM holdings WHERE account_id = ? AND ticker = ?",
            (account_id, ticker),
        ).fetchone()
        return Holding.from_row(row)


def update_holding_from_trade(
    conn, account_id: int, ticker: str, action: str, shares: float, price: float
) -> None:
    """Update a holding based on a BUY or SELL trade.

    Called internally by transaction_service within its DB transaction.
    Takes a connection parameter to share the same transaction.
    """
    ticker = ticker.upper()
    existing = conn.execute(
        "SELECT * FROM holdings WHERE account_id = ? AND ticker = ?",
        (account_id, ticker),
    ).fetchone()

    if action == "BUY":
        if existing:
            old_shares = existing["shares"]
            old_cost = existing["avg_cost"]
            new_shares = old_shares + shares
            new_avg_cost = (
                (old_shares * old_cost) + (shares * price)
            ) / new_shares
            conn.execute(
                """UPDATE holdings
                   SET shares = ?, avg_cost = ?, updated_at = datetime('now')
                   WHERE account_id = ? AND ticker = ?""",
                (new_shares, new_avg_cost, account_id, ticker),
            )
        else:
            conn.execute(
                """INSERT INTO holdings (account_id, ticker, shares, avg_cost)
                   VALUES (?, ?, ?, ?)""",
                (account_id, ticker, shares, price),
            )

    elif action == "SELL":
        if not existing or existing["shares"] < shares:
            current = existing["shares"] if existing else 0
            raise ValueError(
                f"Cannot sell {shares} shares of {ticker}, only {current} held"
            )
        new_shares = existing["shares"] - shares
        if new_shares == 0:
            conn.execute(
                "DELETE FROM holdings WHERE account_id = ? AND ticker = ?",
                (account_id, ticker),
            )
        else:
            # avg_cost stays the same on SELL
            conn.execute(
                """UPDATE holdings
                   SET shares = ?, updated_at = datetime('now')
                   WHERE account_id = ? AND ticker = ?""",
                (new_shares, account_id, ticker),
            )


def get_holding(account_id: int, ticker: str):
    """Get a single holding. Returns None if not found."""
    ticker = ticker.upper()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM holdings WHERE account_id = ? AND ticker = ?",
            (account_id, ticker),
        ).fetchone()
        return Holding.from_row(row) if row else None


def list_holdings(account_id: int) -> list[Holding]:
    """List all holdings in an account."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM holdings WHERE account_id = ? AND shares > 0 ORDER BY ticker",
            (account_id,),
        ).fetchall()
        return [Holding.from_row(r) for r in rows]


def remove_holding(account_id: int, ticker: str) -> None:
    """Remove a holding entirely from an account."""
    ticker = ticker.upper()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM holdings WHERE account_id = ? AND ticker = ?",
            (account_id, ticker),
        )
