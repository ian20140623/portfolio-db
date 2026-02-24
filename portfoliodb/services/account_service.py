"""Account management: create, list, deactivate accounts."""

from portfoliodb.db import get_connection
from portfoliodb.models import Account
from portfoliodb.utils.constants import MARKETS, MARKET_CURRENCY, ACCOUNT_TYPES


def create_account(
    user_id: int,
    account_name: str,
    broker: str,
    market: str,
    account_type: str = "brokerage",
) -> Account:
    """Create a new account for a user.

    Args:
        user_id: Owner user ID
        account_name: Display name (e.g. "Fubon TW Brokerage")
        broker: Broker name (e.g. "Fubon", "Interactive Brokers")
        market: Market code - "TW", "US", or "SG"
        account_type: "brokerage" or "bank"
    """
    market = market.upper()
    if market not in MARKETS:
        raise ValueError(f"Invalid market '{market}'. Must be one of: {', '.join(MARKETS)}")
    if account_type not in ACCOUNT_TYPES:
        raise ValueError(f"Invalid account type '{account_type}'. Must be one of: {', '.join(ACCOUNT_TYPES)}")

    # Auto-assign currency based on market
    currency = MARKET_CURRENCY[market]

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO accounts (user_id, account_name, broker, market, currency, account_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, account_name, broker, market, currency, account_type),
        )
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return Account.from_row(row)


def get_account(account_id: int) -> Account:
    """Get an account by ID. Raises if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Account ID {account_id} not found")
        return Account.from_row(row)


def list_accounts(user_id: int = None) -> list[Account]:
    """List accounts, optionally filtered by user."""
    with get_connection() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ? AND is_active = 1 ORDER BY id",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE is_active = 1 ORDER BY id"
            ).fetchall()
        return [Account.from_row(r) for r in rows]


def deactivate_account(account_id: int) -> None:
    """Soft-delete an account by setting is_active = 0."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE accounts SET is_active = 0 WHERE id = ?", (account_id,)
        )
