"""Formatting helpers for currency, P&L, and percentages."""

from portfoliodb.utils.constants import CURRENCY_SYMBOLS


def format_currency(amount: float, currency: str) -> str:
    """Format amount with currency symbol. e.g. NT$1,234,567.00"""
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), "$")
    if currency.upper() == "TWD":
        # TWD usually shows without decimals for large amounts
        if abs(amount) >= 1:
            return f"{symbol}{amount:,.0f}"
        return f"{symbol}{amount:,.2f}"
    return f"{symbol}{amount:,.2f}"


def format_pnl(amount: float, currency: str) -> str:
    """Format P&L with +/- prefix."""
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), "$")
    sign = "+" if amount >= 0 else ""
    if currency.upper() == "TWD":
        return f"{sign}{symbol}{amount:,.0f}"
    return f"{sign}{symbol}{amount:,.2f}"


def format_percent(pct: float) -> str:
    """Format percentage with +/- prefix. e.g. +12.34%"""
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def format_shares(shares: float, market: str = "US") -> str:
    """Format share count. Integer for TW, decimal for US/SG."""
    if market == "TW" and shares == int(shares):
        return f"{int(shares):,}"
    if shares == int(shares):
        return f"{int(shares):,}"
    return f"{shares:,.4f}"


def pnl_color(amount: float) -> str:
    """Return rich color tag based on P&L direction."""
    if amount > 0:
        return "green"
    elif amount < 0:
        return "red"
    return "white"
