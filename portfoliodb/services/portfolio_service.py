"""Portfolio aggregation: summaries, P&L calculations across accounts."""

from portfoliodb.services import (
    account_service,
    holding_service,
    cash_service,
    price_service,
    fx_service,
)
from portfoliodb.services.user_service import get_user_by_username
from portfoliodb.utils.ticker import detect_market


def get_account_summary(account_id: int) -> dict:
    """Get full summary for a single account.

    Returns:
        {
            "account": Account,
            "holdings": [{"holding": Holding, "current_price": float,
                          "market_value": float, "unrealized_pnl": float,
                          "pnl_pct": float}, ...],
            "cash": [CashPosition, ...],
            "total_stock_value": float,
            "total_cash_value": float,
            "total_value": float,
            "currency": str,
        }
    """
    account = account_service.get_account(account_id)
    holdings = holding_service.list_holdings(account_id)
    cash_positions = cash_service.list_cash(account_id)

    # Fetch prices for all holdings
    tickers = [h.ticker for h in holdings]
    prices = price_service.fetch_prices(tickers) if tickers else {}

    holding_details = []
    total_stock_value = 0

    for h in holdings:
        price_info = prices.get(h.ticker, {})
        current_price = price_info.get("price")

        if current_price is not None:
            market_value = current_price * h.shares
            cost_basis = h.avg_cost * h.shares
            unrealized_pnl = market_value - cost_basis
            pnl_pct = ((current_price / h.avg_cost) - 1) * 100 if h.avg_cost > 0 else 0
            total_stock_value += market_value
        else:
            market_value = None
            unrealized_pnl = None
            pnl_pct = None

        holding_details.append({
            "holding": h,
            "current_price": current_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
        })

    # Sum cash in account's primary currency
    total_cash = sum(cp.balance for cp in cash_positions if cp.currency == account.currency)

    return {
        "account": account,
        "holdings": holding_details,
        "cash": cash_positions,
        "total_stock_value": total_stock_value,
        "total_cash_value": total_cash,
        "total_value": total_stock_value + total_cash,
        "currency": account.currency,
    }


def get_user_summary(username: str, base_currency: str = "TWD") -> dict:
    """Get summary across all accounts for a user, converted to base currency.

    Returns:
        {
            "user": User,
            "accounts": [account_summary, ...],
            "grand_total": float,  (in base_currency)
            "base_currency": str,
        }
    """
    user = get_user_by_username(username)
    accounts = account_service.list_accounts(user_id=user.id)

    # Pre-fetch FX rates
    fx_rates = fx_service.get_all_rates(base_currency)

    account_summaries = []
    grand_total = 0

    for acc in accounts:
        summary = get_account_summary(acc.id)
        # Convert account total to base currency
        rate = fx_rates.get(acc.currency, 1.0)
        converted_total = summary["total_value"] * rate
        summary["converted_total"] = converted_total
        summary["fx_rate"] = rate
        grand_total += converted_total
        account_summaries.append(summary)

    return {
        "user": user,
        "accounts": account_summaries,
        "grand_total": grand_total,
        "base_currency": base_currency,
    }


def get_total_summary(base_currency: str = "TWD") -> dict:
    """Get summary across ALL users and accounts.

    Returns:
        {
            "users": [user_summary, ...],
            "grand_total": float,
            "base_currency": str,
        }
    """
    from portfoliodb.services.user_service import list_users

    users = list_users()
    fx_rates = fx_service.get_all_rates(base_currency)

    user_summaries = []
    grand_total = 0

    for u in users:
        user_sum = get_user_summary(u.username, base_currency)
        grand_total += user_sum["grand_total"]
        user_summaries.append(user_sum)

    return {
        "users": user_summaries,
        "grand_total": grand_total,
        "base_currency": base_currency,
    }
