"""Account management: create, list, deactivate accounts."""

from portfoliodb.db import get_connection
from portfoliodb.models import Account
from portfoliodb.utils.constants import MARKETS, MARKET_CURRENCY, ACCOUNT_TYPES


def create_account(
    legal_owner_id: int,
    economic_owner_id: int,
    account_name: str,
    broker: str,
    market: str,
    account_type: str = "brokerage",
) -> Account:
    """Create a new account.

    Args:
        legal_owner_id: 法律名義人 user ID（戶頭掛在誰名下）
        economic_owner_id: 實際擁有人 user ID（誰的錢／誰承擔損益）
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

    currency = MARKET_CURRENCY[market]

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO accounts
                 (legal_owner_id, economic_owner_id, account_name, broker, market, currency, account_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (legal_owner_id, economic_owner_id, account_name, broker, market, currency, account_type),
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


def list_accounts(
    legal_owner_id: int = None,
    economic_owner_id: int = None,
) -> list[Account]:
    """List accounts, optionally filtered by legal or economic owner."""
    clauses = ["is_active = 1"]
    params: list = []
    if legal_owner_id is not None:
        clauses.append("legal_owner_id = ?")
        params.append(legal_owner_id)
    if economic_owner_id is not None:
        clauses.append("economic_owner_id = ?")
        params.append(economic_owner_id)
    sql = f"SELECT * FROM accounts WHERE {' AND '.join(clauses)} ORDER BY id"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [Account.from_row(r) for r in rows]


def deactivate_account(account_id: int) -> None:
    """Soft-delete an account by setting is_active = 0."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE accounts SET is_active = 0 WHERE id = ?", (account_id,)
        )
