"""Domain model dataclasses for PortfolioDB."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    username: str
    display_name: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "User":
        return cls(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            created_at=row["created_at"],
        )


@dataclass
class Account:
    id: int
    user_id: int
    account_name: str
    broker: str
    market: str
    currency: str
    account_type: str
    is_active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Account":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            account_name=row["account_name"],
            broker=row["broker"],
            market=row["market"],
            currency=row["currency"],
            account_type=row["account_type"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )


@dataclass
class Holding:
    id: int
    account_id: int
    ticker: str
    shares: float
    avg_cost: float
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "Holding":
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            ticker=row["ticker"],
            shares=row["shares"],
            avg_cost=row["avg_cost"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class Transaction:
    id: int
    account_id: int
    ticker: str
    action: str
    shares: float
    price: float
    fee: float
    tax: float
    currency: str
    notes: Optional[str]
    executed_at: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Transaction":
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            ticker=row["ticker"],
            action=row["action"],
            shares=row["shares"],
            price=row["price"],
            fee=row["fee"],
            tax=row["tax"],
            currency=row["currency"],
            notes=row["notes"],
            executed_at=row["executed_at"],
            created_at=row["created_at"],
        )


@dataclass
class CashPosition:
    id: int
    account_id: int
    currency: str
    balance: float
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "CashPosition":
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            currency=row["currency"],
            balance=row["balance"],
            updated_at=row["updated_at"],
        )


@dataclass
class CashTransaction:
    id: int
    account_id: int
    currency: str
    amount: float
    category: str
    description: Optional[str]
    executed_at: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "CashTransaction":
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            currency=row["currency"],
            amount=row["amount"],
            category=row["category"],
            description=row["description"],
            executed_at=row["executed_at"],
            created_at=row["created_at"],
        )


@dataclass
class PlannedOrder:
    id: int
    account_id: int
    ticker: str
    action: str
    shares: float
    target_price: Optional[float]
    reason: Optional[str]
    priority: str
    status: str
    created_at: str
    executed_at: Optional[str]
    linked_transaction_id: Optional[int]

    @classmethod
    def from_row(cls, row) -> "PlannedOrder":
        return cls(
            id=row["id"],
            account_id=row["account_id"],
            ticker=row["ticker"],
            action=row["action"],
            shares=row["shares"],
            target_price=row["target_price"],
            reason=row["reason"],
            priority=row["priority"],
            status=row["status"],
            created_at=row["created_at"],
            executed_at=row["executed_at"],
            linked_transaction_id=row["linked_transaction_id"],
        )
