"""Firstrade CSV transaction history importer.

Firstrade CSV format (downloaded from Accounts > Tax Center > Excel CSV Files):

    Date,Symbol,Type,Quantity,Price,Amount
    02/20/2026,AAPL,BUY,10,178.50,"1,785.00"
    02/15/2026,NVDA,SELL,5,850.00,"4,250.00"
    02/10/2026,,DIVIDEND,0,0.00,25.50
    01/05/2026,,DEPOSIT,0,0.00,"5,000.00"

Notes:
    - Amounts over 1,000 have commas inside quotes: "1,785.00"
    - DIVIDEND/DEPOSIT/WITHDRAWAL rows have empty Symbol
    - Date format: MM/DD/YYYY
"""

import csv
from pathlib import Path
from datetime import datetime


def parse_firstrade_csv(file_path: str) -> dict:
    """Parse a Firstrade CSV file into structured data.

    Returns:
        {
            "transactions": [
                {"date": "2026-02-20", "ticker": "AAPL", "action": "BUY",
                 "shares": 10.0, "price": 178.50, "amount": 1785.00},
                ...
            ],
            "cash_movements": [
                {"date": "2026-02-10", "category": "DIVIDEND", "amount": 25.50,
                 "description": "DIVIDEND"},
                {"date": "2026-01-05", "category": "DEPOSIT", "amount": 5000.00,
                 "description": "DEPOSIT"},
                ...
            ],
            "current_holdings": {
                "AAPL": {"shares": 10.0, "total_cost": 1785.00},
                ...
            },
            "cash_balance": float,  # computed from all movements
        }
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    transactions = []
    cash_movements = []

    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Clean amount field (remove commas from quoted values)
            amount_str = row.get("Amount", "0").replace(",", "").strip()
            amount = float(amount_str) if amount_str else 0.0

            date_str = row.get("Date", "").strip()
            if not date_str:
                continue

            # Convert MM/DD/YYYY to YYYY-MM-DD
            try:
                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                date_iso = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                # Try other date formats
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    date_iso = date_str
                except ValueError:
                    continue  # Skip unparseable rows

            symbol = row.get("Symbol", "").strip().upper()
            tx_type = row.get("Type", "").strip().upper()
            quantity_str = row.get("Quantity", "0").replace(",", "").strip()
            quantity = float(quantity_str) if quantity_str else 0.0
            price_str = row.get("Price", "0").replace(",", "").strip()
            price = float(price_str) if price_str else 0.0

            if tx_type in ("BUY", "SELL") and symbol:
                transactions.append({
                    "date": date_iso,
                    "ticker": symbol,
                    "action": tx_type,
                    "shares": abs(quantity),
                    "price": abs(price),
                    "amount": abs(amount),
                })
            elif tx_type in ("DIVIDEND", "INTEREST"):
                cash_movements.append({
                    "date": date_iso,
                    "category": tx_type,
                    "amount": abs(amount),
                    "description": f"{tx_type}" + (f" - {symbol}" if symbol else ""),
                })
            elif tx_type in ("DEPOSIT", "ACH DEPOSIT", "WIRE DEPOSIT"):
                cash_movements.append({
                    "date": date_iso,
                    "category": "DEPOSIT",
                    "amount": abs(amount),
                    "description": tx_type,
                })
            elif tx_type in ("WITHDRAWAL", "ACH WITHDRAWAL", "WIRE WITHDRAWAL"):
                cash_movements.append({
                    "date": date_iso,
                    "category": "WITHDRAWAL",
                    "amount": -abs(amount),
                    "description": tx_type,
                })
            elif tx_type == "FEE":
                cash_movements.append({
                    "date": date_iso,
                    "category": "FEE",
                    "amount": -abs(amount),
                    "description": f"FEE" + (f" - {symbol}" if symbol else ""),
                })

    # Compute current holdings from transactions
    holdings = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        ticker = tx["ticker"]
        if ticker not in holdings:
            holdings[ticker] = {"shares": 0.0, "total_cost": 0.0}

        if tx["action"] == "BUY":
            holdings[ticker]["shares"] += tx["shares"]
            holdings[ticker]["total_cost"] += tx["shares"] * tx["price"]
        elif tx["action"] == "SELL":
            holdings[ticker]["shares"] -= tx["shares"]
            if holdings[ticker]["shares"] <= 0:
                holdings[ticker] = {"shares": 0.0, "total_cost": 0.0}

    # Remove tickers with 0 shares
    holdings = {k: v for k, v in holdings.items() if v["shares"] > 0}

    # Compute cash balance
    cash_balance = sum(m["amount"] for m in cash_movements)
    # Subtract stock purchases, add stock sales
    for tx in transactions:
        if tx["action"] == "BUY":
            cash_balance -= tx["amount"]
        elif tx["action"] == "SELL":
            cash_balance += tx["amount"]

    return {
        "transactions": transactions,
        "cash_movements": cash_movements,
        "current_holdings": holdings,
        "cash_balance": cash_balance,
    }
