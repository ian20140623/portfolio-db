"""Planned orders management: create, list, execute, cancel."""

from portfoliodb.db import get_connection
from portfoliodb.models import PlannedOrder
from portfoliodb.services.transaction_service import record_transaction
from portfoliodb.utils.constants import TRANSACTION_ACTIONS, ORDER_PRIORITIES, ORDER_STATUSES


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
    ticker = ticker.upper()
    priority = priority.upper()

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
