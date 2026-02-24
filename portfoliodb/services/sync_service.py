"""Sync service: pull data from broker APIs and CSV imports into the database."""

from portfoliodb.services import holding_service, cash_service, account_service
from portfoliodb.db import get_connection


def sync_broker_holdings(account_id: int, holdings_data: list[dict]) -> dict:
    """Sync holdings from a broker API into the database.

    Replaces all existing holdings for this account with fresh data from broker.

    Args:
        account_id: Target account ID in our database
        holdings_data: List from broker.get_holdings(), each dict has:
            {"ticker": "2330.TW", "shares": 1000, "avg_cost": 580.5, ...}

    Returns:
        {"added": int, "updated": int, "removed": int}
    """
    account = account_service.get_account(account_id)
    existing = holding_service.list_holdings(account_id)
    existing_map = {h.ticker: h for h in existing}

    broker_tickers = set()
    added = 0
    updated = 0

    with get_connection() as conn:
        for item in holdings_data:
            ticker = item["ticker"].upper()
            shares = item["shares"]
            avg_cost = item["avg_cost"]
            broker_tickers.add(ticker)

            if shares <= 0:
                continue

            if ticker in existing_map:
                # Update existing holding
                old = existing_map[ticker]
                if old.shares != shares or abs(old.avg_cost - avg_cost) > 0.01:
                    conn.execute(
                        """UPDATE holdings
                           SET shares = ?, avg_cost = ?, updated_at = datetime('now')
                           WHERE account_id = ? AND ticker = ?""",
                        (shares, avg_cost, account_id, ticker),
                    )
                    updated += 1
            else:
                # Add new holding
                conn.execute(
                    """INSERT INTO holdings (account_id, ticker, shares, avg_cost)
                       VALUES (?, ?, ?, ?)""",
                    (account_id, ticker, shares, avg_cost),
                )
                added += 1

    # Remove holdings no longer in broker data
    removed = 0
    for ticker, h in existing_map.items():
        if ticker not in broker_tickers:
            holding_service.remove_holding(account_id, ticker)
            removed += 1

    return {"added": added, "updated": updated, "removed": removed}


def sync_broker_cash(account_id: int, balance_data: dict) -> None:
    """Sync cash balance from broker API.

    Args:
        account_id: Target account ID
        balance_data: From broker.get_balance(), e.g.
            {"balance": 500000.0, "currency": "TWD"}
    """
    cash_service.set_cash(
        account_id,
        balance_data["currency"],
        balance_data["balance"],
    )


def sync_sinopac(account_id: int) -> dict:
    """Full sync from SinoPac Securities (永豐金).

    Args:
        account_id: The account ID mapped to this SinoPac account

    Returns:
        {"holdings": {"added": N, "updated": N, "removed": N}, "cash_synced": True}
    """
    from portfoliodb.brokers.sinopac_broker import SinoPacBroker

    broker = SinoPacBroker()
    broker.login()

    try:
        holdings = broker.get_holdings()
        balance = broker.get_balance()

        result = sync_broker_holdings(account_id, holdings)
        sync_broker_cash(account_id, balance)

        return {"holdings": result, "cash_synced": True}
    finally:
        broker.logout()


def sync_fubon(account_id: int) -> dict:
    """Full sync from Fubon Securities (富邦證券).

    Args:
        account_id: The account ID mapped to this Fubon account

    Returns:
        {"holdings": {"added": N, "updated": N, "removed": N}, "cash_synced": True}
    """
    from portfoliodb.brokers.fubon_broker import FubonBroker

    broker = FubonBroker()
    broker.login()

    holdings = broker.get_holdings()
    balance = broker.get_balance()

    result = sync_broker_holdings(account_id, holdings)
    sync_broker_cash(account_id, balance)

    return {"holdings": result, "cash_synced": True}


def import_firstrade_csv(account_id: int, csv_path: str) -> dict:
    """Import holdings and cash from a Firstrade CSV export.

    Args:
        account_id: The account ID mapped to Firstrade
        csv_path: Path to the downloaded CSV file

    Returns:
        {"holdings_imported": int, "cash_set": True, "transactions_imported": int}
    """
    from portfoliodb.importers.firstrade_csv import parse_firstrade_csv

    data = parse_firstrade_csv(csv_path)

    # Sync holdings (computed from transaction history)
    holdings_data = []
    for ticker, info in data["current_holdings"].items():
        avg_cost = info["total_cost"] / info["shares"] if info["shares"] > 0 else 0
        holdings_data.append({
            "ticker": ticker,
            "shares": info["shares"],
            "avg_cost": avg_cost,
        })

    result = sync_broker_holdings(account_id, holdings_data)

    # Set cash balance
    cash_service.set_cash(account_id, "USD", data["cash_balance"])

    return {
        "holdings_imported": result["added"] + result["updated"],
        "cash_set": True,
        "transactions_count": len(data["transactions"]),
        "cash_movements_count": len(data["cash_movements"]),
    }


def import_scb_csv(account_id: int, csv_path: str) -> dict:
    """Import cash balance from a Standard Chartered SG CSV export.

    Note: SCB CSV only contains bank transactions, not stock holdings.
    Stock holdings for SCB need to be managed separately.

    Args:
        account_id: The account ID mapped to SCB SG
        csv_path: Path to the downloaded CSV file

    Returns:
        {"cash_balance": float, "currency": str, "transactions_count": int}
    """
    from portfoliodb.importers.scb_csv import parse_scb_csv

    data = parse_scb_csv(csv_path)

    # Set the current cash balance
    cash_service.set_cash(account_id, data["currency"], data["current_balance"])

    return {
        "cash_balance": data["current_balance"],
        "currency": data["currency"],
        "transactions_count": len(data["transactions"]),
    }
