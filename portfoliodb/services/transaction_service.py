"""Transaction service: record buy/sell trades with double-entry (stock + cash)."""

from portfoliodb.db import get_connection
from portfoliodb.models import Transaction
from portfoliodb.services.holding_service import update_holding_from_trade
from portfoliodb.services.cash_service import adjust_cash
from portfoliodb.services.account_service import get_account
from portfoliodb.utils.constants import TRANSACTION_ACTIONS


def record_transaction(
    account_id: int,
    ticker: str,
    action: str,
    shares: float,
    price: float,
    fee: float = 0,
    tax: float = 0,
    executed_at: str = None,
    notes: str = None,
) -> Transaction:
    """Record a stock trade and update holdings + cash atomically.

    BUY: holdings shares increase, cash decreases by (shares * price + fee + tax)
    SELL: holdings shares decrease, cash increases by (shares * price - fee - tax)
    """
    action = action.upper()
    ticker = ticker.upper()
    if action not in TRANSACTION_ACTIONS:
        raise ValueError(f"Invalid action '{action}'. Must be BUY or SELL")
    if shares <= 0:
        raise ValueError("Shares must be positive")
    if price <= 0:
        raise ValueError("Price must be positive")

    # Get account to determine currency
    account = get_account(account_id)
    currency = account.currency

    with get_connection() as conn:
        # 1. Update holdings
        update_holding_from_trade(conn, account_id, ticker, action, shares, price)

        # 2. Update cash
        total_cost = shares * price
        if action == "BUY":
            cash_change = -(total_cost + fee + tax)
        else:  # SELL
            cash_change = total_cost - fee - tax
        adjust_cash(conn, account_id, currency, cash_change)

        # 3. Record the transaction
        if executed_at is None:
            cursor = conn.execute(
                """INSERT INTO transactions
                   (account_id, ticker, action, shares, price, fee, tax, currency, notes, executed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (account_id, ticker, action, shares, price, fee, tax, currency, notes),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO transactions
                   (account_id, ticker, action, shares, price, fee, tax, currency, notes, executed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, ticker, action, shares, price, fee, tax, currency, notes, executed_at),
            )

        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return Transaction.from_row(row)


def list_transactions(
    account_id: int = None,
    ticker: str = None,
    limit: int = 50,
) -> list[Transaction]:
    """List transactions with optional filters."""
    conditions = []
    params = []

    if account_id is not None:
        conditions.append("account_id = ?")
        params.append(account_id)
    if ticker is not None:
        conditions.append("ticker = ?")
        params.append(ticker.upper())

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM transactions {where} ORDER BY executed_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [Transaction.from_row(r) for r in rows]


def get_transaction(transaction_id: int) -> Transaction:
    """Get a single transaction by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Transaction ID {transaction_id} not found")
        return Transaction.from_row(row)
