"""Cash position management: deposits, withdrawals, and balance tracking."""

from portfoliodb.db import get_connection
from portfoliodb.models import CashPosition, CashTransaction
from portfoliodb.utils.constants import CURRENCIES, CASH_CATEGORIES


def set_cash(account_id: int, currency: str, balance: float) -> CashPosition:
    """Set cash balance directly (for initial setup/import)."""
    currency = currency.upper()
    if currency not in CURRENCIES:
        raise ValueError(f"Invalid currency '{currency}'. Must be one of: {', '.join(CURRENCIES)}")

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO cash_positions (account_id, currency, balance)
               VALUES (?, ?, ?)
               ON CONFLICT(account_id, currency)
               DO UPDATE SET balance = ?, updated_at = datetime('now')""",
            (account_id, currency, balance, balance),
        )
        row = conn.execute(
            "SELECT * FROM cash_positions WHERE account_id = ? AND currency = ?",
            (account_id, currency),
        ).fetchone()
        return CashPosition.from_row(row)


def adjust_cash(conn, account_id: int, currency: str, amount: float) -> None:
    """Adjust cash balance by amount (positive = add, negative = subtract).

    Takes a connection parameter to share DB transaction with transaction_service.
    """
    currency = currency.upper()
    existing = conn.execute(
        "SELECT * FROM cash_positions WHERE account_id = ? AND currency = ?",
        (account_id, currency),
    ).fetchone()

    if existing:
        new_balance = existing["balance"] + amount
        conn.execute(
            """UPDATE cash_positions
               SET balance = ?, updated_at = datetime('now')
               WHERE account_id = ? AND currency = ?""",
            (new_balance, account_id, currency),
        )
    else:
        conn.execute(
            """INSERT INTO cash_positions (account_id, currency, balance)
               VALUES (?, ?, ?)""",
            (account_id, currency, amount),
        )


def get_cash(account_id: int, currency: str):
    """Get cash position for a specific currency. Returns None if not found."""
    currency = currency.upper()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM cash_positions WHERE account_id = ? AND currency = ?",
            (account_id, currency),
        ).fetchone()
        return CashPosition.from_row(row) if row else None


def list_cash(account_id: int) -> list[CashPosition]:
    """List all cash positions in an account."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cash_positions WHERE account_id = ? ORDER BY currency",
            (account_id,),
        ).fetchall()
        return [CashPosition.from_row(r) for r in rows]


def record_cash_transaction(
    account_id: int,
    currency: str,
    amount: float,
    category: str,
    description: str = None,
    executed_at: str = None,
) -> CashTransaction:
    """Record a cash movement (deposit, withdrawal, dividend, etc.) and update balance."""
    currency = currency.upper()
    category = category.upper()
    if currency not in CURRENCIES:
        raise ValueError(f"Invalid currency '{currency}'")
    if category not in CASH_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {', '.join(CASH_CATEGORIES)}")

    if executed_at is None:
        executed_at = "datetime('now')"
        use_raw = True
    else:
        use_raw = False

    with get_connection() as conn:
        # Update cash balance
        adjust_cash(conn, account_id, currency, amount)

        # Record the cash transaction
        if use_raw:
            cursor = conn.execute(
                """INSERT INTO cash_transactions
                   (account_id, currency, amount, category, description, executed_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (account_id, currency, amount, category, description),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO cash_transactions
                   (account_id, currency, amount, category, description, executed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (account_id, currency, amount, category, description, executed_at),
            )

        row = conn.execute(
            "SELECT * FROM cash_transactions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return CashTransaction.from_row(row)
