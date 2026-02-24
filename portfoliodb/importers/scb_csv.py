"""Standard Chartered Bank Singapore CSV importer.

SCB SG CSV format (downloaded from Online Banking > Account > Download as CSV):

The file has 5 header rows before the actual data:
    Row 1: "Account transactions from DD/MM/YYYY to DD/MM/YYYY"
    Row 2: Account Name
    Row 3: Account Number
    Row 4: Currency
    Row 5: "Current Balance","Available Balance"
    Row 6: Column headers
    Row 7+: Data

Data columns:
    Date,Transaction,Currency,Deposit,Withdrawal,Running Balance,SGD Equivalent Balance

Notes:
    - Date format: DD/MM/YYYY
    - Amounts may be quoted with commas: "3,129.92 CR"
    - Running Balance has " CR" suffix
"""

import csv
from pathlib import Path
from datetime import datetime


def parse_scb_csv(file_path: str) -> dict:
    """Parse a Standard Chartered Bank SG CSV file.

    Returns:
        {
            "account_name": str,
            "account_number": str,
            "currency": str,
            "current_balance": float,
            "transactions": [
                {"date": "2026-02-20", "description": "WITHDRAWAL",
                 "currency": "SGD", "amount": -500.00, "balance": 4500.00},
                ...
            ],
            "cash_movements": [
                {"date": "2026-02-20", "category": "WITHDRAWAL",
                 "amount": -500.00, "description": "WITHDRAWAL"},
                ...
            ],
        }
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    if len(lines) < 7:
        raise ValueError("CSV file too short — expected at least 7 rows (5 header + header row + data)")

    # Parse header metadata
    account_name = lines[1].strip().strip('"')
    account_number = lines[2].strip().strip('"')
    currency = lines[3].strip().strip('"').upper()

    # Parse balance from row 5
    balance_parts = lines[4].strip().split(",")
    current_balance = _parse_scb_amount(balance_parts[0]) if balance_parts else 0.0

    # Parse data rows (skip first 5 header rows + column header row)
    transactions = []
    cash_movements = []

    # Use csv reader for the data portion
    data_lines = lines[5:]  # Skip metadata rows
    reader = csv.DictReader(data_lines)

    for row in reader:
        date_str = row.get("Date", "").strip()
        if not date_str:
            continue

        # Convert DD/MM/YYYY to YYYY-MM-DD
        try:
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue

        description = row.get("Transaction", "").strip()
        row_currency = row.get("Currency", currency).strip().upper()

        deposit_str = row.get("Deposit", "").strip()
        withdrawal_str = row.get("Withdrawal", "").strip()
        balance_str = row.get("Running Balance", "").strip()

        deposit = _parse_scb_amount(deposit_str) if deposit_str else 0.0
        withdrawal = _parse_scb_amount(withdrawal_str) if withdrawal_str else 0.0
        running_balance = _parse_scb_amount(balance_str) if balance_str else 0.0

        # Determine amount (positive for deposit, negative for withdrawal)
        if deposit > 0:
            amount = deposit
        elif withdrawal > 0:
            amount = -withdrawal
        else:
            amount = 0.0

        transactions.append({
            "date": date_iso,
            "description": description,
            "currency": row_currency,
            "amount": amount,
            "balance": running_balance,
        })

        # Categorize for cash_movements
        category = _categorize_scb_transaction(description)
        cash_movements.append({
            "date": date_iso,
            "category": category,
            "amount": amount,
            "description": description,
        })

    return {
        "account_name": account_name,
        "account_number": account_number,
        "currency": currency,
        "current_balance": current_balance,
        "transactions": transactions,
        "cash_movements": cash_movements,
    }


def _parse_scb_amount(text: str) -> float:
    """Parse SCB amount string like '"3,129.92 CR"' -> 3129.92"""
    text = text.strip().strip('"').replace(",", "")
    text = text.replace(" CR", "").replace(" DR", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _categorize_scb_transaction(description: str) -> str:
    """Categorize an SCB transaction description."""
    desc = description.upper()
    if "INTEREST" in desc or "CR INTEREST" in desc:
        return "INTEREST"
    elif "DIVIDEND" in desc:
        return "DIVIDEND"
    elif "WITHDRAWAL" in desc or "ATM" in desc:
        return "WITHDRAWAL"
    elif "DEPOSIT" in desc or "SALARY" in desc or "TRANSFER IN" in desc:
        return "DEPOSIT"
    elif "FEE" in desc or "CHARGE" in desc:
        return "FEE"
    elif "FX" in desc or "EXCHANGE" in desc:
        return "FX_CONVERSION"
    else:
        # Default: if amount is positive it's a deposit, negative is withdrawal
        return "DEPOSIT"
