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

    # FX rates for converting holding prices to account currency (handles
    # cross-currency positions like USD stocks in an SGD account).
    fx_rates_for_acc = fx_service.get_all_rates(account.currency)

    holding_details = []
    total_stock_value = 0

    for h in holdings:
        price_info = prices.get(h.ticker, {})
        current_price = price_info.get("price")
        # Use the price's own currency (e.g. USD for NVDA), not account currency.
        price_currency = price_info.get("currency") or account.currency

        if current_price is not None:
            if price_currency != account.currency:
                fx = fx_rates_for_acc.get(price_currency, 1.0)
                market_value = current_price * h.shares * fx
            else:
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
    """Get summary across all accounts where this user is the **economic owner**,
    converted to base currency.

    Reflects真實 portfolio (誰的錢)，not legal name on file.
    """
    user = get_user_by_username(username)
    accounts = account_service.list_accounts(economic_owner_id=user.id)

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


def get_family_breakdown(base_currency: str = "TWD") -> dict:
    """Family-wide flat breakdown: every position (stock + cash) across all accounts,
    plus multi-dimensional aggregations.

    Used for top-down portfolio review: concentration, owner split, currency mix, etc.
    """
    from portfoliodb.services.user_service import get_user

    accounts = account_service.list_accounts()
    fx_rates = fx_service.get_all_rates(base_currency)
    user_cache: dict[int, str] = {}

    def name_of(uid: int) -> str:
        if uid not in user_cache:
            user_cache[uid] = get_user(uid).display_name
        return user_cache[uid]

    positions: list[dict] = []

    for acc in accounts:
        holdings = holding_service.list_holdings(acc.id)
        cash_positions = cash_service.list_cash(acc.id)
        rate = fx_rates.get(acc.currency, 1.0)

        if holdings:
            prices = price_service.fetch_prices([h.ticker for h in holdings])
        else:
            prices = {}

        for h in holdings:
            price_info = prices.get(h.ticker, {})
            current = price_info.get("price")
            # Use the price's own currency so cross-currency positions
            # (e.g. USD stocks in an SGD account) convert correctly to TWD.
            price_currency = price_info.get("currency") or acc.currency
            price_rate = fx_rates.get(price_currency, 1.0)
            mv_local = (current or 0) * h.shares
            mv_base = mv_local * price_rate
            positions.append({
                "type": "stock", "ticker": h.ticker,
                "shares": h.shares, "avg_cost": h.avg_cost,
                "current_price": current,
                "currency": price_currency,
                "mv_local": mv_local, "mv_base": mv_base,
                "account_id": acc.id, "account_name": acc.account_name,
                "broker": acc.broker, "market": acc.market,
                "account_type": acc.account_type,
                "legal_owner": name_of(acc.legal_owner_id),
                "economic_owner": name_of(acc.economic_owner_id),
            })

        for cp in cash_positions:
            cp_rate = fx_rates.get(cp.currency, 1.0)
            positions.append({
                "type": "cash", "ticker": cp.currency,
                "shares": None, "avg_cost": None, "current_price": None,
                "currency": cp.currency,
                "mv_local": cp.balance, "mv_base": cp.balance * cp_rate,
                "account_id": acc.id, "account_name": acc.account_name,
                "broker": acc.broker, "market": acc.market,
                "account_type": acc.account_type,
                "legal_owner": name_of(acc.legal_owner_id),
                "economic_owner": name_of(acc.economic_owner_id),
            })

    positions.sort(key=lambda p: -p["mv_base"])
    grand_total = sum(p["mv_base"] for p in positions)

    for p in positions:
        p["weight"] = (p["mv_base"] / grand_total * 100) if grand_total else 0

    def _group(key_fn):
        groups: dict = {}
        for p in positions:
            k = key_fn(p)
            groups[k] = groups.get(k, 0) + p["mv_base"]
        return dict(sorted(groups.items(), key=lambda x: -x[1]))

    aggregations = {
        "by_economic_owner": _group(lambda p: p["economic_owner"]),
        "by_legal_owner":    _group(lambda p: p["legal_owner"]),
        "by_type":           _group(lambda p: p["type"]),
        "by_currency":       _group(lambda p: p["currency"]),
        "by_market":         _group(lambda p: p["market"]),
        "by_broker":         _group(lambda p: p["broker"]),
        "by_account_type":   _group(lambda p: p["account_type"]),
        # Ticker-level concentration: stocks only, merged across accounts
        "by_ticker": dict(sorted(
            ((t, sum(p["mv_base"] for p in positions if p["type"]=="stock" and p["ticker"]==t))
             for t in {p["ticker"] for p in positions if p["type"]=="stock"}),
            key=lambda x: -x[1],
        )),
    }

    # Pending order intents per ticker — used by `summary breakdown` to annotate
    # individual stock rows with the user's planned next move. Minimal friction:
    # just a single-line shorthand "→加 500 @1180" or "→減 200".
    #
    # JOIN key is the **canonical instrument-layer ticker** so a pending order
    # written as "2330" (legacy) lines up with the holding row stored as
    # "2330.TW". ADR vs common share stay distinct: TSM intents never collide
    # with 2330.TW intents.
    from portfoliodb.db import get_connection
    from portfoliodb.utils.ticker import canonical_ticker
    pending_intents: dict = {}
    with get_connection() as conn:
        for row in conn.execute(
            "SELECT po.ticker, po.action, po.shares, po.target_price, "
            "       a.market AS account_market "
            "FROM planned_orders po "
            "LEFT JOIN accounts a ON po.account_id = a.id "
            "WHERE po.status = 'PENDING' ORDER BY po.created_at"
        ):
            canon, _ = canonical_ticker(row["ticker"], market_hint=row["account_market"])
            sign = "加" if row["action"] == "BUY" else "減"
            price_str = f" @{row['target_price']:g}" if row["target_price"] else ""
            label = f"→{sign} {row['shares']:,.0f}{price_str}"
            pending_intents.setdefault(canon, []).append(label)

    return {
        "positions": positions,
        "aggregations": aggregations,
        "pending_intents": pending_intents,
        "grand_total": grand_total,
        "base_currency": base_currency,
        "fx_rates": fx_rates,
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
