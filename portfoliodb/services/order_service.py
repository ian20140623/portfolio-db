"""Planned orders management: create, list, execute, cancel."""

from portfoliodb.db import get_connection
from portfoliodb.models import PlannedOrder
from portfoliodb.services.transaction_service import record_transaction
from portfoliodb.utils.constants import TRANSACTION_ACTIONS, ORDER_PRIORITIES, ORDER_STATUSES
from portfoliodb.utils.ticker import canonical_ticker


def create_order(
    account_id: int,
    ticker: str,
    action: str,
    shares: float,
    target_price: float = None,
    reason: str = None,
    priority: str = "NORMAL",
) -> PlannedOrder:
    """Create a new planned order."""
    action = action.upper()
    priority = priority.upper()

    # Single source of truth for ticker normalisation: canonical_ticker().
    # Use the owning account's market as the hint so "2330" written under a
    # TW account becomes "2330.TW"; ambiguous cases (8/6/9 digit prefix) come
    # back unresolved and Sir is expected to write the suffix explicitly.
    from portfoliodb.services.account_service import get_account
    market_hint = None
    try:
        market_hint = get_account(account_id).market
    except Exception:
        pass  # account_id invalid is caught downstream by FK constraint
    ticker, unresolved = canonical_ticker(ticker, market_hint=market_hint)
    if unresolved:
        raise ValueError(
            f"Cannot canonicalise ticker '{ticker}': {unresolved}. "
            "Please write the suffix explicitly (e.g. 2330.TW or 8299.TWO)."
        )

    if action not in TRANSACTION_ACTIONS:
        raise ValueError(f"Invalid action '{action}'. Must be BUY or SELL")
    if priority not in ORDER_PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'. Must be one of: {', '.join(ORDER_PRIORITIES)}")

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO planned_orders
               (account_id, ticker, action, shares, target_price, reason, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account_id, ticker, action, shares, target_price, reason, priority),
        )
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return PlannedOrder.from_row(row)


def list_orders(
    account_id: int = None,
    status: str = "PENDING",
) -> list[PlannedOrder]:
    """List planned orders with optional filters."""
    conditions = []
    params = []

    if account_id is not None:
        conditions.append("account_id = ?")
        params.append(account_id)
    if status is not None:
        conditions.append("status = ?")
        params.append(status.upper())

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM planned_orders {where} ORDER BY priority DESC, created_at"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [PlannedOrder.from_row(r) for r in rows]


def execute_order(
    order_id: int,
    actual_price: float,
    fee: float = 0,
    tax: float = 0,
) -> PlannedOrder:
    """Execute a planned order: create real transaction and link it."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Order ID {order_id} not found")

        order = PlannedOrder.from_row(row)
        if order.status != "PENDING":
            raise ValueError(f"Order is already {order.status}")

    # Record the actual transaction
    tx = record_transaction(
        account_id=order.account_id,
        ticker=order.ticker,
        action=order.action,
        shares=order.shares,
        price=actual_price,
        fee=fee,
        tax=tax,
        notes=f"Executed from planned order #{order_id}",
    )

    # Update order status
    with get_connection() as conn:
        conn.execute(
            """UPDATE planned_orders
               SET status = 'EXECUTED', executed_at = datetime('now'),
                   linked_transaction_id = ?
               WHERE id = ?""",
            (tx.id, order_id),
        )
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (order_id,)
        ).fetchone()
        return PlannedOrder.from_row(row)


def cancel_order(order_id: int) -> PlannedOrder:
    """Cancel a pending planned order."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Order ID {order_id} not found")
        if row["status"] != "PENDING":
            raise ValueError(f"Order is already {row['status']}")

        conn.execute(
            "UPDATE planned_orders SET status = 'CANCELLED' WHERE id = ?",
            (order_id,),
        )
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (order_id,)
        ).fetchone()
        return PlannedOrder.from_row(row)


def review_orders(since_days: int = 180) -> dict:
    """Retrospective view of planned orders — pure mechanical stats, no scoring.

    Returns 4 stat views (per Athena design doctrine, 2026-05-26):
      1. counts: total / executed / cancelled / pending by status
      2. unexecuted_with_outcome: PENDING/CANCELLED orders + current price (did stock move?)
      3. execution_lag: for EXECUTED orders, days from create to execute
      4. repeated_tickers: tickers that appear in multiple orders (recurring intent)

    All ticker comparison is done on the **canonical instrument-layer key**
    via `canonical_ticker()` — pre-2026-05-26 rows where the suffix is
    missing get normalised at read time so they aggregate alongside their
    suffixed counterparts. Migration 001 backfills the stored column, so on
    a migrated DB the runtime normalisation is a no-op safety net.
    """
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=since_days)).strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT po.*, a.market AS account_market "
            "FROM planned_orders po "
            "LEFT JOIN accounts a ON po.account_id = a.id "
            "WHERE po.created_at >= ? ORDER BY po.created_at DESC",
            (cutoff,),
        ).fetchall()

    orders = []
    for r in rows:
        o = dict(r)
        canon, _ = canonical_ticker(o["ticker"], market_hint=o.get("account_market"))
        o["ticker"] = canon  # canonical for both presentation and aggregation
        orders.append(o)

    counts = {"total": len(orders), "PENDING": 0, "EXECUTED": 0, "CANCELLED": 0}
    for o in orders:
        counts[o["status"]] = counts.get(o["status"], 0) + 1

    execution_lag_days = []
    for o in orders:
        if o["status"] == "EXECUTED" and o["executed_at"]:
            created = datetime.fromisoformat(o["created_at"].replace(" ", "T"))
            executed = datetime.fromisoformat(o["executed_at"].replace(" ", "T"))
            execution_lag_days.append({
                "order_id": o["id"], "ticker": o["ticker"],
                "days": (executed - created).total_seconds() / 86400,
            })

    ticker_counts: dict[str, int] = {}
    for o in orders:
        ticker_counts[o["ticker"]] = ticker_counts.get(o["ticker"], 0) + 1
    repeated = sorted(
        [(t, c) for t, c in ticker_counts.items() if c > 1],
        key=lambda x: -x[1],
    )

    unexecuted = [o for o in orders if o["status"] in ("PENDING", "CANCELLED")]

    return {
        "since_days": since_days,
        "counts": counts,
        "execution_lag": execution_lag_days,
        "repeated_tickers": repeated,
        "unexecuted": unexecuted,
    }


def update_order(order_id: int, **kwargs) -> PlannedOrder:
    """Update fields of a pending planned order."""
    allowed = {"ticker", "action", "shares", "target_price", "reason", "priority"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

    if not updates:
        raise ValueError("No valid fields to update")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Order ID {order_id} not found")
        if row["status"] != "PENDING":
            raise ValueError(f"Cannot update order with status {row['status']}")

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [order_id]
        conn.execute(
            f"UPDATE planned_orders SET {set_clause} WHERE id = ?", params
        )
        row = conn.execute(
            "SELECT * FROM planned_orders WHERE id = ?", (order_id,)
        ).fetchone()
        return PlannedOrder.from_row(row)
