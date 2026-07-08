"""CLI entry point for PortfolioDB."""

from datetime import datetime

import click
from rich.console import Console
from rich.table import Table

from portfoliodb.db import init_db, DB_PATH
from portfoliodb.utils.formatting import (
    format_currency, format_pnl, format_percent, format_shares, pnl_color,
)
from portfoliodb.utils.constants import CURRENCIES, CURRENCY_SYMBOLS

console = Console()


# ─── Root command group ──────────────────────────────────────────────

@click.group()
def cli():
    """PortfolioDB - Multi-Account Portfolio Management System"""
    pass


# ─── init ────────────────────────────────────────────────────────────

@cli.command()
def init():
    """Initialize the database (create tables)."""
    init_db()
    console.print(f"[green][OK][/green] Database initialized at {DB_PATH}")


# ─── backup commands ─────────────────────────────────────────────────

@cli.group(invoke_without_command=True)
@click.pass_context
def backup(ctx):
    """Off-machine DB cold backup (Dropbox). Bare `backup` snapshots now."""
    if ctx.invoked_subcommand is not None:
        return
    from portfoliodb.backup import create_backup
    path = create_backup()
    if path is None:
        console.print("[yellow]No database found; nothing to back up.[/yellow]")
        console.print(f"[dim]Expected at: {DB_PATH}[/dim]")
        return
    console.print(
        f"[green][OK][/green] Backup created: {path.name} "
        f"({path.stat().st_size:,} bytes)"
    )
    console.print(f"[dim]{path.parent}[/dim]")


@backup.command("list")
def backup_list():
    """List available cold backups (newest first)."""
    from portfoliodb.backup import list_backups, backup_dir
    items = list_backups()
    if not items:
        console.print(f"[yellow]No backups in {backup_dir()}[/yellow]")
        return
    table = Table(title=f"Backups in {backup_dir()} ({len(items)})")
    table.add_column("File")
    table.add_column("Size", justify="right")
    table.add_column("Modified")
    for p in items:
        st = p.stat()
        table.add_row(
            p.name,
            f"{st.st_size:,}",
            datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@backup.command("restore")
@click.argument("filename", required=False)
@click.option("--force", is_flag=True,
              help="Overwrite existing DB (current DB saved to pre-restore copy first)")
def backup_restore(filename, force):
    """Restore a backup into the live DB. No FILENAME = newest backup."""
    from portfoliodb.backup import list_backups, restore_backup, backup_dir
    if filename is None:
        items = list_backups()
        if not items:
            console.print(f"[red]No backups available in {backup_dir()}[/red]")
            return
        src = items[0]
        console.print(f"[dim]No file given; using newest: {src.name}[/dim]")
    else:
        src = backup_dir() / filename
    try:
        dest = restore_backup(src, force=force)
    except FileExistsError as e:
        console.print(f"[red]Refused:[/red] {e}")
        return
    except FileNotFoundError as e:
        console.print(f"[red]Not found:[/red] {e}")
        return
    console.print(f"[green][OK][/green] Restored {src.name} → {dest}")


# ─── user commands ───────────────────────────────────────────────────

@cli.group()
def user():
    """User management."""
    pass


@user.command("add")
@click.argument("username")
@click.argument("display_name")
def user_add(username, display_name):
    """Create a new user."""
    from portfoliodb.services.user_service import create_user
    try:
        u = create_user(username, display_name)
        console.print(f"[green][OK][/green] User created: {u.username} ({u.display_name})")
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@user.command("list")
def user_list():
    """List all users."""
    from portfoliodb.services.user_service import list_users
    users = list_users()
    if not users:
        console.print("No users found. Use [bold]user add[/bold] to create one.")
        return

    table = Table(title="Users")
    table.add_column("ID", style="cyan")
    table.add_column("Username", style="bold")
    table.add_column("Display Name")
    table.add_column("Created")
    for u in users:
        table.add_row(str(u.id), u.username, u.display_name, u.created_at)
    console.print(table)


# ─── account commands ────────────────────────────────────────────────

@cli.group()
def account():
    """Account management."""
    pass


@account.command("add")
@click.argument("legal_owner")
@click.argument("account_name")
@click.argument("broker")
@click.argument("market", type=click.Choice(["TW", "US", "SG"], case_sensitive=False))
@click.option("--economic-owner", "economic_owner", default=None,
              help="實際擁有人 username（不給=同 legal_owner）")
@click.option("--type", "account_type", default="brokerage",
              type=click.Choice(["brokerage", "bank"]), help="Account type")
def account_add(legal_owner, account_name, broker, market, economic_owner, account_type):
    """Create an account.

    LEGAL_OWNER = 戶頭掛在誰名下；--economic-owner = 實際是誰的錢（預設同 legal）

    Examples:
      account add ian "Firstrade" Firstrade US
      account add dad "Fubon TW" Fubon TW --economic-owner ian
    """
    from portfoliodb.services.user_service import get_user_by_username
    from portfoliodb.services.account_service import create_account
    try:
        legal = get_user_by_username(legal_owner)
        economic = get_user_by_username(economic_owner) if economic_owner else legal
        acc = create_account(
            legal.id, economic.id, account_name, broker,
            market.upper(), account_type,
        )
        same = legal.id == economic.id
        owner_label = legal.display_name if same else f"{legal.display_name} → {economic.display_name}"
        console.print(
            f"[green][OK][/green] Account created: {acc.account_name} "
            f"({acc.broker}, {acc.market}/{acc.currency}, owner: {owner_label}) "
            f"[bold][ID: {acc.id}][/bold]"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@account.command("list")
@click.option("--legal", "legal_username", default=None, help="Filter by legal owner")
@click.option("--economic", "economic_username", default=None,
              help="Filter by economic owner（誰的錢）")
def account_list(legal_username, economic_username):
    """List accounts."""
    from portfoliodb.services.account_service import list_accounts
    from portfoliodb.services.user_service import get_user, get_user_by_username

    legal_id = get_user_by_username(legal_username).id if legal_username else None
    economic_id = get_user_by_username(economic_username).id if economic_username else None

    accounts = list_accounts(legal_owner_id=legal_id, economic_owner_id=economic_id)
    if not accounts:
        console.print("No accounts found.")
        return

    user_cache = {}
    def name_of(uid):
        if uid not in user_cache:
            user_cache[uid] = get_user(uid).display_name
        return user_cache[uid]

    table = Table(title="Accounts")
    table.add_column("ID", style="cyan")
    table.add_column("Legal Owner")
    table.add_column("Economic Owner")
    table.add_column("Account Name", style="bold")
    table.add_column("Broker")
    table.add_column("Market")
    table.add_column("Currency")
    table.add_column("Type")
    for a in accounts:
        table.add_row(
            str(a.id),
            name_of(a.legal_owner_id),
            name_of(a.economic_owner_id),
            a.account_name, a.broker, a.market, a.currency, a.account_type,
        )
    console.print(table)


# ─── holding commands ────────────────────────────────────────────────

@cli.group()
def holding():
    """Holdings management."""
    pass


@holding.command("add")
@click.argument("account_id", type=int)
@click.argument("ticker")
@click.argument("shares", type=float)
@click.argument("avg_cost", type=float)
def holding_add(account_id, ticker, shares, avg_cost):
    """Import a holding. Example: holding add 1 2330.TW 1000 580.5"""
    from portfoliodb.services.holding_service import add_holding
    from portfoliodb.services.account_service import get_account
    try:
        acc = get_account(account_id)
        h = add_holding(account_id, ticker, shares, avg_cost)
        console.print(
            f"[green][OK][/green] Added: {h.ticker} x {format_shares(h.shares)} shares "
            f"@ {format_currency(h.avg_cost, acc.currency)} avg cost"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@holding.command("list")
@click.argument("account_id", type=int)
def holding_list(account_id):
    """List holdings in an account."""
    from portfoliodb.services.holding_service import list_holdings
    from portfoliodb.services.account_service import get_account

    acc = get_account(account_id)
    holdings = list_holdings(account_id)
    if not holdings:
        console.print(f"No holdings in account {acc.account_name}.")
        return

    table = Table(title=f"Holdings - {acc.account_name}")
    table.add_column("Ticker", style="bold")
    table.add_column("Shares", justify="right")
    table.add_column("Avg Cost", justify="right")
    for h in holdings:
        table.add_row(
            h.ticker,
            format_shares(h.shares, acc.market),
            format_currency(h.avg_cost, acc.currency),
        )
    console.print(table)


@holding.command("remove")
@click.argument("account_id", type=int)
@click.argument("ticker")
def holding_remove(account_id, ticker):
    """Remove a holding from an account."""
    from portfoliodb.services.holding_service import remove_holding
    try:
        remove_holding(account_id, ticker)
        console.print(f"[green][OK][/green] Removed {ticker.upper()} from account {account_id}")
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


# ─── transaction commands ────────────────────────────────────────────

@cli.group()
def tx():
    """Transaction management (buy/sell)."""
    pass


@tx.command("buy")
@click.argument("account_id", type=int)
@click.argument("ticker")
@click.argument("shares", type=float)
@click.argument("price", type=float)
@click.option("--fee", default=0.0, help="Commission/fee")
@click.option("--tax", default=0.0, help="Transaction tax")
@click.option("--date", "executed_at", default=None, help="Trade date (YYYY-MM-DD)")
@click.option("--note", "notes", default=None, help="Optional note")
def tx_buy(account_id, ticker, shares, price, fee, tax, executed_at, notes):
    """Record a BUY transaction."""
    from portfoliodb.services.transaction_service import record_transaction
    from portfoliodb.services.account_service import get_account
    try:
        acc = get_account(account_id)
        t = record_transaction(account_id, ticker, "BUY", shares, price, fee, tax, executed_at, notes)
        total = shares * price + fee + tax
        console.print(
            f"[green][OK][/green] BUY: {format_shares(shares)} shares of {t.ticker} "
            f"@ {format_currency(price, acc.currency)} "
            f"(total: {format_currency(total, acc.currency)})"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@tx.command("sell")
@click.argument("account_id", type=int)
@click.argument("ticker")
@click.argument("shares", type=float)
@click.argument("price", type=float)
@click.option("--fee", default=0.0, help="Commission/fee")
@click.option("--tax", default=0.0, help="Transaction tax")
@click.option("--date", "executed_at", default=None, help="Trade date (YYYY-MM-DD)")
@click.option("--note", "notes", default=None, help="Optional note")
def tx_sell(account_id, ticker, shares, price, fee, tax, executed_at, notes):
    """Record a SELL transaction."""
    from portfoliodb.services.transaction_service import record_transaction
    from portfoliodb.services.account_service import get_account
    try:
        acc = get_account(account_id)
        t = record_transaction(account_id, ticker, "SELL", shares, price, fee, tax, executed_at, notes)
        total = shares * price - fee - tax
        console.print(
            f"[green][OK][/green] SELL: {format_shares(shares)} shares of {t.ticker} "
            f"@ {format_currency(price, acc.currency)} "
            f"(net: {format_currency(total, acc.currency)})"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@tx.command("list")
@click.option("--account", "account_id", type=int, default=None, help="Filter by account ID")
@click.option("--ticker", default=None, help="Filter by ticker")
@click.option("--limit", default=20, help="Max records to show")
def tx_list(account_id, ticker, limit):
    """List transaction history."""
    from portfoliodb.services.transaction_service import list_transactions

    txns = list_transactions(account_id=account_id, ticker=ticker, limit=limit)
    if not txns:
        console.print("No transactions found.")
        return

    table = Table(title="Transactions")
    table.add_column("ID", style="cyan")
    table.add_column("Date")
    table.add_column("Action")
    table.add_column("Ticker", style="bold")
    table.add_column("Shares", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Fee", justify="right")
    table.add_column("Tax", justify="right")
    table.add_column("Note")
    for t in txns:
        action_color = "green" if t.action == "BUY" else "red"
        table.add_row(
            str(t.id), t.executed_at,
            f"[{action_color}]{t.action}[/{action_color}]",
            t.ticker,
            f"{t.shares:,.2f}", f"{t.price:,.2f}",
            f"{t.fee:,.2f}", f"{t.tax:,.2f}",
            t.notes or "",
        )
    console.print(table)


# ─── cash commands ───────────────────────────────────────────────────

@cli.group()
def cash():
    """Cash position management."""
    pass


@cash.command("set")
@click.argument("account_id", type=int)
@click.argument("currency", type=click.Choice(sorted(CURRENCIES), case_sensitive=False))
@click.argument("amount", type=float)
def cash_set(account_id, currency, amount):
    """Set cash balance directly. Example: cash set 1 TWD 500000"""
    from portfoliodb.services.cash_service import set_cash
    from portfoliodb.services.account_service import get_account
    try:
        acc = get_account(account_id)
        cp = set_cash(account_id, currency.upper(), amount)
        console.print(
            f"[green][OK][/green] Cash set: {format_currency(cp.balance, cp.currency)} "
            f"in {acc.account_name}"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@cash.command("deposit")
@click.argument("account_id", type=int)
@click.argument("currency", type=click.Choice(sorted(CURRENCIES), case_sensitive=False))
@click.argument("amount", type=float)
@click.option("--date", "executed_at", default=None, help="Date (YYYY-MM-DD)")
@click.option("--desc", "description", default=None, help="Description")
def cash_deposit(account_id, currency, amount, executed_at, description):
    """Deposit cash into account."""
    from portfoliodb.services.cash_service import record_cash_transaction
    try:
        ct = record_cash_transaction(
            account_id, currency.upper(), abs(amount), "DEPOSIT", description, executed_at
        )
        console.print(
            f"[green][OK][/green] Deposited {format_currency(abs(amount), currency.upper())}"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@cash.command("withdraw")
@click.argument("account_id", type=int)
@click.argument("currency", type=click.Choice(sorted(CURRENCIES), case_sensitive=False))
@click.argument("amount", type=float)
@click.option("--date", "executed_at", default=None, help="Date (YYYY-MM-DD)")
@click.option("--desc", "description", default=None, help="Description")
def cash_withdraw(account_id, currency, amount, executed_at, description):
    """Withdraw cash from account."""
    from portfoliodb.services.cash_service import record_cash_transaction
    try:
        ct = record_cash_transaction(
            account_id, currency.upper(), -abs(amount), "WITHDRAWAL", description, executed_at
        )
        console.print(
            f"[green][OK][/green] Withdrew {format_currency(abs(amount), currency.upper())}"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@cash.command("list")
@click.argument("account_id", type=int)
def cash_list(account_id):
    """List cash positions in an account."""
    from portfoliodb.services.cash_service import list_cash
    from portfoliodb.services.account_service import get_account

    acc = get_account(account_id)
    positions = list_cash(account_id)
    if not positions:
        console.print(f"No cash in account {acc.account_name}.")
        return

    table = Table(title=f"Cash - {acc.account_name}")
    table.add_column("Currency", style="bold")
    table.add_column("Balance", justify="right")
    for cp in positions:
        table.add_row(cp.currency, format_currency(cp.balance, cp.currency))
    console.print(table)


# ─── order commands ──────────────────────────────────────────────────

@cli.group()
def order():
    """Planned orders management."""
    pass


@order.command("add", context_settings={"ignore_unknown_options": True})
@click.argument("account_id", type=int)
@click.argument("ticker")
@click.argument("shares", type=str)
@click.option("--price", "target_price", type=float, default=None, help="Target price")
@click.option("--reason", default=None, help="Reason for this order")
@click.option("--priority", default="NORMAL",
              type=click.Choice(["HIGH", "NORMAL", "LOW"], case_sensitive=False))
def order_add(account_id, ticker, shares, target_price, reason, priority):
    """Create a planned order. SHARES = signed shorthand (+N buy, -N sell) or 'buy N'/'sell N'.

    Examples:
      order add 3 2330 +1000 --price 1180 --reason "AI 加碼"
      order add 1 2383 -1000 --price 5400 --reason "trim"
      order add 1 2383 sell 1000 --price 5400   (alternative for shells eating leading -)
    """
    from portfoliodb.services.order_service import create_order
    import sys
    s = shares.strip().lower()
    action = None
    n = None
    if s.startswith("+"):
        action, n = "BUY", float(s[1:])
    elif s.startswith("-") and len(s) > 1 and s[1].isdigit():
        action, n = "SELL", float(s[1:])
    elif s in ("buy", "sell", "b", "s"):
        # legacy explicit form: "buy 1000" / "sell 500" — next positional is shares
        # Click consumed shares as the keyword、real shares 在 sys.argv 下一個
        # 不過 click 沒幫我 capture、要 fallback: read sys.argv directly
        try:
            idx = sys.argv.index(shares)
            n = float(sys.argv[idx + 1])
            action = "BUY" if s.startswith("b") else "SELL"
        except (ValueError, IndexError):
            console.print(f"[red][ERROR][/red] usage: order add <account_id> <ticker> buy|sell <shares>")
            return
    else:
        console.print(f"[red][ERROR][/red] SHARES must be '+1000' (buy), '-500' (sell), or 'buy 1000'/'sell 500'")
        return
    try:
        o = create_order(account_id, ticker, action, n, target_price, reason, priority)
        price_str = f"@ {o.target_price:,.2f}" if o.target_price else "@ market"
        sign = "+" if o.action == "BUY" else "-"
        console.print(
            f"[green][OK][/green] Planned order [bold][ID: {o.id}][/bold]: "
            f"{o.ticker} {sign}{format_shares(o.shares)} {price_str} "
            f"({o.priority}{', ' + o.reason if o.reason else ''})"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@order.command("list")
@click.option("--account", "account_id", type=int, default=None, help="Filter by account")
@click.option("--status", default="PENDING",
              type=click.Choice(["PENDING", "EXECUTED", "CANCELLED", "ALL"], case_sensitive=False))
def order_list(account_id, status):
    """List planned orders."""
    from portfoliodb.services.order_service import list_orders

    status_filter = None if status == "ALL" else status
    orders = list_orders(account_id=account_id, status=status_filter)
    if not orders:
        console.print("No orders found.")
        return

    table = Table(title="Planned Orders")
    table.add_column("ID", style="cyan")
    table.add_column("Ticker", style="bold")
    table.add_column("Action")
    table.add_column("Shares", justify="right")
    table.add_column("Target Price", justify="right")
    table.add_column("Priority")
    table.add_column("Status")
    table.add_column("Reason")
    for o in orders:
        action_color = "green" if o.action == "BUY" else "red"
        price_str = f"{o.target_price:,.2f}" if o.target_price else "market"
        status_color = {"PENDING": "yellow", "EXECUTED": "green", "CANCELLED": "dim"}.get(o.status, "white")
        table.add_row(
            str(o.id), o.ticker,
            f"[{action_color}]{o.action}[/{action_color}]",
            f"{o.shares:,.2f}", price_str,
            o.priority,
            f"[{status_color}]{o.status}[/{status_color}]",
            o.reason or "",
        )
    console.print(table)


@order.command("execute")
@click.argument("order_id", type=int)
@click.argument("actual_price", type=float)
@click.option("--fee", default=0.0, help="Commission/fee")
@click.option("--tax", default=0.0, help="Transaction tax")
def order_execute(order_id, actual_price, fee, tax):
    """Execute a planned order at actual price."""
    from portfoliodb.services.order_service import execute_order
    try:
        o = execute_order(order_id, actual_price, fee, tax)
        console.print(
            f"[green][OK][/green] Order #{o.id} executed: "
            f"{o.action} {format_shares(o.shares)} shares {o.ticker} @ {actual_price:,.2f}"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@order.command("cancel")
@click.argument("order_id", type=int)
def order_cancel(order_id):
    """Cancel a pending planned order."""
    from portfoliodb.services.order_service import cancel_order
    try:
        o = cancel_order(order_id)
        console.print(f"[green][OK][/green] Order #{o.id} cancelled")
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@order.command("review")
@click.option("--since", "since_days", type=int, default=180,
              help="Look back N days (default 180)")
def order_review(since_days):
    """Retrospective stats — counts, lag, repeated tickers, unexecuted outcomes."""
    from portfoliodb.services.order_service import review_orders
    from portfoliodb.services.price_service import fetch_prices

    r = review_orders(since_days=since_days)
    console.print()
    console.rule(f"[bold] Order Review — past {r['since_days']} days [/bold]")

    c = r["counts"]
    console.print(f"\n[bold]Counts[/bold]: total={c['total']}  "
                  f"PENDING=[yellow]{c['PENDING']}[/yellow]  "
                  f"EXECUTED=[green]{c['EXECUTED']}[/green]  "
                  f"CANCELLED=[dim]{c['CANCELLED']}[/dim]")

    if r["execution_lag"]:
        console.print(f"\n[bold]Execution lag (create → execute)[/bold]")
        t = Table()
        t.add_column("Order ID"); t.add_column("Ticker")
        t.add_column("Days", justify="right")
        for e in r["execution_lag"]:
            t.add_row(str(e["order_id"]), e["ticker"], f"{e['days']:.1f}")
        console.print(t)

    if r["repeated_tickers"]:
        console.print(f"\n[bold]反覆出現的個股[/bold]（心裡惦記但未必下手）")
        for ticker, count in r["repeated_tickers"]:
            console.print(f"  {ticker}: {count} 次")

    if r["unexecuted"]:
        console.print(f"\n[bold]未執行 plan + 當前股價對照[/bold]")
        tickers = list({o["ticker"] for o in r["unexecuted"]})
        prices = fetch_prices(tickers) if tickers else {}
        t = Table()
        t.add_column("ID"); t.add_column("Ticker"); t.add_column("Action")
        t.add_column("Shares", justify="right"); t.add_column("Target", justify="right")
        t.add_column("現價", justify="right"); t.add_column("Status"); t.add_column("Reason")
        for o in r["unexecuted"]:
            cur = prices.get(o["ticker"], {}).get("price")
            cur_str = f"{cur:.2f}" if cur is not None else "—"
            target_str = f"{o['target_price']:.2f}" if o["target_price"] else "market"
            t.add_row(
                str(o["id"]), o["ticker"], o["action"],
                f"{o['shares']:,.0f}", target_str, cur_str,
                f"[dim]{o['status']}[/dim]", o["reason"] or "",
            )
        console.print(t)

        # Data-quality warnings (e.g. yfinance returned no quote) — surfaced
        # so a missing price is flagged rather than hidden, but kept out of
        # the main table so it doesn't disrupt the price-alignment scan.
        warnings = [
            (k, v.get("warning"))
            for k, v in prices.items()
            if v.get("warning")
        ]
        if warnings:
            joined = "、".join(f"{tk} ({w})" for tk, w in warnings)
            console.print(f"[dim]Data warnings: {joined}[/dim]")

    if c["total"] == 0:
        console.print("\n[dim]無 order data 可 review。先用 `order add` 寫幾個 plan、累積 data。[/dim]")


# ─── rank commands ────────────────────────────────────────────────────

@cli.group()
def rank():
    """Individual-stock ranking snapshots (PEG / Kelly f* / 15-point framework)."""
    pass


@rank.command("add")
@click.argument("ticker")
@click.argument("method", type=click.Choice(["peg", "kelly", "fifteen_point"], case_sensitive=False))
@click.argument("headline_score", type=float)
@click.option("--date", "score_date", default=None,
              help="Date the ranking reflects (YYYY-MM-DD). Default: today")
@click.option("--weight", "weight_pct", type=float, default=None,
              help="Suggested portfolio weight percent, e.g. 21 for 21% (mainly Kelly)")
@click.option("--source", default=None, help="Citation, e.g. '7/6 投研 session'")
@click.option("--notes", default=None, help="Supporting detail (G/FwdPE, b/G-trajectory, dimension breakdown)")
@click.option("--market", "market_hint", default=None,
              type=click.Choice(["TW", "US", "SG"], case_sensitive=False),
              help="Market hint for bare-digit TW tickers starting with 2/3 (e.g. 2330 + --market TW). "
                   "Tickers starting with 6/8/9 are ambiguous (上市/上櫃) — write the suffix explicitly instead.")
@click.option("--framework-version", "method_version", default=None,
              help="Which iteration of the methodology produced this score (e.g. 'V1', 'V1.1'). "
                   "The framework is a living doc, not frozen — tag it so later analysis doesn't "
                   "conflate scores from different rule sets. Optional but encouraged.")
def rank_add(ticker, method, headline_score, score_date, weight_pct, source, notes, market_hint, method_version):
    """Record a ranking snapshot. Example: rank add NVDA kelly 0.85 --weight 21 --source "7/6 投研 session\""""
    from portfoliodb.services.ranking_service import add_ranking
    if score_date is None:
        score_date = datetime.now().strftime("%Y-%m-%d")
    try:
        r = add_ranking(
            ticker, method, score_date, headline_score,
            weight_pct=weight_pct, source=source, notes=notes, market_hint=market_hint,
            method_version=method_version,
        )
        version_tag = f" [{r.method_version}]" if r.method_version else ""
        console.print(f"[green][OK][/green] {r.ticker} {r.method}{version_tag} @ {r.score_date}: {r.headline_score}")
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@rank.command("list")
@click.option("--method", type=click.Choice(["peg", "kelly", "fifteen_point"], case_sensitive=False),
              default=None, help="Filter by method; without this, latest-only ranking is skipped")
@click.option("--ticker", default=None, help="Filter by ticker")
@click.option("--latest", is_flag=True, help="Show only the latest snapshot per ticker, ranked best-to-worst")
def rank_list(method, ticker, latest):
    """List ranking snapshots."""
    from portfoliodb.services.ranking_service import list_rankings, latest_rankings

    if latest:
        if method is None:
            console.print("[red][ERROR][/red] --latest requires --method (direction of \"better\" is method-specific)")
            return
        rows = latest_rankings(method)
    else:
        rows = list_rankings(method=method, ticker=ticker)

    if not rows:
        console.print("[dim]無 ranking data。先用 `rank add` 記幾筆。[/dim]")
        return

    t = Table()
    if latest:
        t.add_column("排名", justify="right")
    t.add_column("Ticker")
    t.add_column("Method")
    t.add_column("Ver")
    t.add_column("Date")
    t.add_column("Score", justify="right")
    t.add_column("Weight%", justify="right")
    t.add_column("Source")
    for i, r in enumerate(rows, start=1):
        row = []
        if latest:
            row.append(str(i))
        row += [
            r.ticker, r.method, r.method_version or "",
            r.score_date,
            f"{r.headline_score:g}" if r.headline_score is not None else "—",
            f"{r.weight_pct:g}" if r.weight_pct is not None else "",
            r.source or "",
        ]
        t.add_row(*row)
    console.print(t)


@rank.command("show")
@click.argument("ticker")
def rank_show(ticker):
    """Full ranking history (all methods) for one ticker."""
    from portfoliodb.services.ranking_service import ticker_history
    rows = ticker_history(ticker)
    if not rows:
        console.print(f"[dim]{ticker}: 無 ranking data。[/dim]")
        return

    t = Table(title=rows[0].ticker)
    t.add_column("Date")
    t.add_column("Method")
    t.add_column("Ver")
    t.add_column("Score", justify="right")
    t.add_column("Weight%", justify="right")
    t.add_column("Source")
    t.add_column("Notes")
    for r in rows:
        t.add_row(
            r.score_date, r.method, r.method_version or "",
            f"{r.headline_score:g}" if r.headline_score is not None else "—",
            f"{r.weight_pct:g}" if r.weight_pct is not None else "",
            r.source or "", r.notes or "",
        )
    console.print(t)


# ─── price commands ──────────────────────────────────────────────────

@cli.group()
def price():
    """Stock price utilities."""
    pass


@price.command("get")
@click.argument("ticker")
def price_get(ticker):
    """Fetch current price for a ticker."""
    from portfoliodb.services.price_service import fetch_price
    try:
        init_db()  # Ensure DB exists for cache
        p = fetch_price(ticker)
        cached_tag = " [dim](cached)[/dim]" if p["cached"] else ""
        console.print(
            f"{ticker.upper()}: {format_currency(p['price'], p['currency'])}{cached_tag}"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@price.command("batch")
@click.argument("tickers", nargs=-1)
def price_batch(tickers):
    """Fetch prices for multiple tickers. Example: price batch 2330.TW AAPL NVDA"""
    from portfoliodb.services.price_service import fetch_prices
    if not tickers:
        console.print("Provide at least one ticker.")
        return

    init_db()
    results = fetch_prices(list(tickers))

    table = Table(title="Stock Prices")
    table.add_column("Ticker", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Currency")
    table.add_column("Status")
    for ticker, info in results.items():
        if info.get("price") is not None:
            table.add_row(
                ticker,
                format_currency(info["price"], info["currency"]),
                info["currency"],
                "[dim]cached[/dim]" if info.get("cached") else "[green]live[/green]",
            )
        else:
            table.add_row(ticker, "-", "-", f"[red]{info.get('error', 'unknown')}[/red]")
    console.print(table)


# ─── summary commands ────────────────────────────────────────────────

@cli.group()
def summary():
    """Portfolio summaries."""
    pass


@summary.command("account")
@click.argument("account_id", type=int)
def summary_account(account_id):
    """Show summary for a single account."""
    from portfoliodb.services.portfolio_service import get_account_summary

    init_db()
    s = get_account_summary(account_id)
    acc = s["account"]
    curr = s["currency"]

    console.print()
    console.rule(f"[bold] Account: {acc.account_name} ({acc.broker}, {acc.market}/{curr}) [/bold]")

    # Holdings table
    if s["holdings"]:
        table = Table(title="Holdings")
        table.add_column("Ticker", style="bold")
        table.add_column("Shares", justify="right")
        table.add_column("Avg Cost", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("Market Value", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Return", justify="right")

        for hd in s["holdings"]:
            h = hd["holding"]
            if hd["current_price"] is not None:
                color = pnl_color(hd["unrealized_pnl"])
                table.add_row(
                    h.ticker,
                    format_shares(h.shares, acc.market),
                    format_currency(h.avg_cost, curr),
                    format_currency(hd["current_price"], curr),
                    format_currency(hd["market_value"], curr),
                    f"[{color}]{format_pnl(hd['unrealized_pnl'], curr)}[/{color}]",
                    f"[{color}]{format_percent(hd['pnl_pct'])}[/{color}]",
                )
            else:
                table.add_row(h.ticker, format_shares(h.shares, acc.market),
                              format_currency(h.avg_cost, curr), "-", "-", "-", "-")
        console.print(table)
    else:
        console.print("[dim]No holdings[/dim]")

    # Cash
    if s["cash"]:
        console.print()
        cash_table = Table(title="Cash")
        cash_table.add_column("Currency", style="bold")
        cash_table.add_column("Balance", justify="right")
        for cp in s["cash"]:
            cash_table.add_row(cp.currency, format_currency(cp.balance, cp.currency))
        console.print(cash_table)

    console.print()
    console.print(f"  Stock Value: [bold]{format_currency(s['total_stock_value'], curr)}[/bold]")
    console.print(f"  Cash Value:  [bold]{format_currency(s['total_cash_value'], curr)}[/bold]")
    console.print(f"  [bold]Total:       {format_currency(s['total_value'], curr)}[/bold]")
    console.print()


@summary.command("user")
@click.argument("username")
@click.option("--currency", "base_currency", default="TWD", help="Base currency for conversion")
def summary_user(username, base_currency):
    """Show summary for all accounts of a user."""
    from portfoliodb.services.portfolio_service import get_user_summary

    init_db()
    s = get_user_summary(username, base_currency.upper())

    console.print()
    console.rule(f"[bold] {s['user'].display_name} ({s['user'].username}) [/bold]")

    for acc_s in s["accounts"]:
        acc = acc_s["account"]
        curr = acc_s["currency"]
        console.print()
        console.print(
            f"  [bold]{acc.account_name}[/bold] ({acc.broker}, {acc.market}) "
            f"- Total: {format_currency(acc_s['total_value'], curr)}"
        )
        if curr != base_currency.upper():
            console.print(
                f"    Converted: {format_currency(acc_s['converted_total'], base_currency.upper())} "
                f"(rate: {acc_s['fx_rate']:.4f})"
            )

        if acc_s["holdings"]:
            for hd in acc_s["holdings"]:
                h = hd["holding"]
                if hd["current_price"] is not None:
                    color = pnl_color(hd["unrealized_pnl"])
                    console.print(
                        f"    {h.ticker:12s} {format_shares(h.shares, acc.market):>10s} shares "
                        f"@ {format_currency(h.avg_cost, curr):>12s} -> "
                        f"{format_currency(hd['current_price'], curr):>12s}  "
                        f"[{color}]{format_pnl(hd['unrealized_pnl'], curr):>12s} "
                        f"({format_percent(hd['pnl_pct'])})[/{color}]"
                    )

    console.print()
    console.print(
        f"  [bold]Grand Total: {format_currency(s['grand_total'], base_currency.upper())}[/bold]"
    )
    console.print()


@summary.command("all")
@click.option("--currency", "base_currency", default="TWD", help="Base currency for conversion")
def summary_all(base_currency):
    """Show summary across ALL users."""
    from portfoliodb.services.portfolio_service import get_total_summary

    init_db()
    s = get_total_summary(base_currency.upper())

    console.print()
    console.rule("[bold] Portfolio Overview - All Users [/bold]")

    for user_s in s["users"]:
        console.print(
            f"\n  [bold]{user_s['user'].display_name}[/bold]: "
            f"{format_currency(user_s['grand_total'], base_currency.upper())}"
        )
        for acc_s in user_s["accounts"]:
            acc = acc_s["account"]
            console.print(
                f"    {acc.account_name:20s} {format_currency(acc_s['total_value'], acc_s['currency']):>15s} "
                f"({acc_s['currency']})"
            )

    console.print()
    console.print(
        f"  [bold]Grand Total: {format_currency(s['grand_total'], base_currency.upper())}[/bold]"
    )
    console.print()


@summary.command("breakdown")
@click.option("--currency", "base_currency", default="TWD", help="Base currency")
def summary_breakdown(base_currency):
    """Family-wide breakdown: every position + multi-dim aggregations."""
    from portfoliodb.services.portfolio_service import get_family_breakdown

    init_db()
    base = base_currency.upper()
    s = get_family_breakdown(base)
    total = s["grand_total"]

    console.print()
    console.rule(f"[bold] Family Portfolio Breakdown ({base}) [/bold]")
    console.print(
        f"  總資產: [bold]{format_currency(total, base)}[/bold]   "
        f"FX: " + ", ".join(f"{c}={r:.4f}" for c, r in s["fx_rates"].items() if c != base)
    )

    labels = {
        "by_economic_owner": "經濟所有人",
        "by_legal_owner":    "法律名義人",
        "by_type":           "資產類別 (stock/cash)",
        "by_currency":       "幣別",
        "by_market":         "市場",
        "by_broker":         "券商/銀行",
        "by_account_type":   "帳戶類型",
        "by_ticker":         "個股 concentration",
    }
    pending_intents = s.get("pending_intents", {})
    for key, label in labels.items():
        t = Table(title=f"by {label}", show_header=True, header_style="bold")
        t.add_column("項目")
        t.add_column(f"{base} 市值", justify="right")
        t.add_column("%", justify="right")
        # Annotate ticker rows with pending order intent (per Athena ship list 2026-05-26)
        if key == "by_ticker":
            t.add_column("intent")
        for k, v in s["aggregations"][key].items():
            pct = v / total * 100 if total else 0
            if key == "by_ticker":
                intent = " / ".join(pending_intents.get(str(k).upper(), [])) or ""
                t.add_row(str(k), format_currency(v, base), f"{pct:.1f}%", intent)
            else:
                t.add_row(str(k), format_currency(v, base), f"{pct:.1f}%")
        console.print(t)

    flat = Table(
        title="Flat positions (every holding + cash, sorted by base-currency value)",
        show_header=True, header_style="bold",
    )
    flat.add_column("#", justify="right", no_wrap=True)
    flat.add_column("類別", no_wrap=True)
    flat.add_column("標的", no_wrap=True)
    flat.add_column("股數", justify="right", no_wrap=True)
    flat.add_column("均價", justify="right", no_wrap=True)
    flat.add_column("現價", justify="right", no_wrap=True)
    flat.add_column("幣", no_wrap=True)
    flat.add_column("原幣市值", justify="right", no_wrap=True)
    flat.add_column(f"{base} 市值", justify="right", no_wrap=True)
    flat.add_column("%", justify="right", no_wrap=True)
    flat.add_column("帳戶", no_wrap=True)
    flat.add_column("econ", no_wrap=True)

    for i, p in enumerate(s["positions"], 1):
        flat.add_row(
            str(i),
            "股票" if p["type"] == "stock" else "現金",
            p["ticker"],
            f"{p['shares']:,.4f}" if p["shares"] is not None else "",
            f"{p['avg_cost']:.4f}" if p["avg_cost"] is not None else "",
            f"{p['current_price']:.2f}" if p["current_price"] is not None else "",
            p["currency"],
            format_currency(p["mv_local"], p["currency"]),
            format_currency(p["mv_base"], base),
            f"{p['weight']:.1f}%",
            p["account_name"],
            p["economic_owner"],
        )
    # Use a wider console for the flat table so columns don't get truncated.
    Console(width=200).print(flat)
    console.print()


# ─── fx commands ─────────────────────────────────────────────────────

@cli.group()
def fx():
    """Exchange rate utilities."""
    pass


@fx.command("rate")
@click.argument("from_currency")
@click.argument("to_currency")
def fx_rate(from_currency, to_currency):
    """Show exchange rate. Example: fx rate USD TWD"""
    from portfoliodb.services.fx_service import fetch_rate
    try:
        init_db()
        rate = fetch_rate(from_currency, to_currency)
        console.print(f"{from_currency.upper()}/{to_currency.upper()} = {rate:.4f}")
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@fx.command("rates")
@click.option("--base", "base_currency", default="TWD", help="Base currency")
def fx_rates(base_currency):
    """Show all exchange rates to base currency."""
    from portfoliodb.services.fx_service import get_all_rates
    try:
        init_db()
        rates = get_all_rates(base_currency.upper())
        table = Table(title=f"Exchange Rates (to {base_currency.upper()})")
        table.add_column("Currency", style="bold")
        table.add_column("Rate", justify="right")
        for curr, rate in sorted(rates.items()):
            table.add_row(curr, f"{rate:.4f}")
        console.print(table)
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


# ─── sync commands (broker API + CSV import) ─────────────────────────

@cli.group()
def sync():
    """Sync data from brokers and CSV files."""
    pass


@sync.command("sinopac")
@click.argument("account_id", type=int)
def sync_sinopac_cmd(account_id):
    """Sync holdings & cash from SinoPac (永豐金) via Shioaji API."""
    from portfoliodb.services.sync_service import sync_sinopac
    try:
        console.print("Connecting to SinoPac (永豐金)...")
        result = sync_sinopac(account_id)
        h = result["holdings"]
        console.print(
            f"[green][OK][/green] SinoPac sync complete: "
            f"{h['added']} added, {h['updated']} updated, {h['removed']} removed"
        )
        if result["cash_synced"]:
            console.print("[green][OK][/green] Cash balance synced")
    except ImportError as e:
        console.print(f"[red][ERROR][/red] {e}")
        console.print("Install with: [bold]pip install shioaji[speed][/bold]")
    except FileNotFoundError as e:
        from portfoliodb.brokers.config import CREDENTIALS_PATH
        console.print(f"[red][ERROR][/red] {e}")
        console.print(
            f"\nCreate credentials file at:\n  {CREDENTIALS_PATH}\n"
            "\nFormat:\n"
            '  {"sinopac": {"api_key": "...", "secret_key": "...", '
            '"ca_path": "...", "ca_password": "..."}}'
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@sync.command("fubon")
@click.argument("account_id", type=int)
def sync_fubon_cmd(account_id):
    """Sync holdings & cash from Fubon (富邦) via Neo API."""
    from portfoliodb.services.sync_service import sync_fubon
    try:
        console.print("Connecting to Fubon (富邦)...")
        result = sync_fubon(account_id)
        h = result["holdings"]
        console.print(
            f"[green][OK][/green] Fubon sync complete: "
            f"{h['added']} added, {h['updated']} updated, {h['removed']} removed"
        )
        if result["cash_synced"]:
            console.print("[green][OK][/green] Cash balance synced")
    except ImportError as e:
        console.print(f"[red][ERROR][/red] {e}")
    except FileNotFoundError as e:
        from portfoliodb.brokers.config import CREDENTIALS_PATH
        console.print(f"[red][ERROR][/red] {e}")
        console.print(
            f"\nCreate credentials file at:\n  {CREDENTIALS_PATH}\n"
            "\nFormat:\n"
            '  {"fubon": {"user_id": "...", "password": "...", '
            '"pfx_path": "...", "pfx_password": "..."}}'
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@sync.command("firstrade")
@click.argument("account_id", type=int)
@click.argument("csv_path", type=click.Path(exists=True))
def sync_firstrade_cmd(account_id, csv_path):
    """Import holdings & cash from Firstrade CSV file.

    Download CSV from: Firstrade > Accounts > Tax Center > Excel CSV Files
    """
    from portfoliodb.services.sync_service import import_firstrade_csv
    try:
        result = import_firstrade_csv(account_id, csv_path)
        console.print(
            f"[green][OK][/green] Firstrade import complete: "
            f"{result['holdings_imported']} holdings, "
            f"{result['transactions_count']} transactions parsed"
        )
        console.print(f"[green][OK][/green] Cash balance set from CSV")
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@sync.command("scb")
@click.argument("account_id", type=int)
@click.argument("csv_path", type=click.Path(exists=True))
def sync_scb_cmd(account_id, csv_path):
    """Import cash balance from Standard Chartered SG CSV file.

    Download CSV from: SCB Online Banking > Account > Download & Print > CSV
    """
    from portfoliodb.services.sync_service import import_scb_csv
    try:
        result = import_scb_csv(account_id, csv_path)
        console.print(
            f"[green][OK][/green] SCB import complete: "
            f"cash {format_currency(result['cash_balance'], result['currency'])}, "
            f"{result['transactions_count']} transactions parsed"
        )
    except Exception as e:
        console.print(f"[red][ERROR][/red] {e}")


@sync.command("credentials")
@click.argument("broker", type=click.Choice(["sinopac", "fubon"]))
def sync_credentials(broker):
    """Setup or check API credentials for a broker."""
    from portfoliodb.brokers.config import has_credentials, CREDENTIALS_PATH, CREDENTIALS_DIR

    if has_credentials(broker):
        console.print(f"[green][OK][/green] Credentials found for {broker}")
    else:
        console.print(f"[yellow]No credentials for {broker}[/yellow]")
        console.print(f"\nCreate the file at:\n  {CREDENTIALS_PATH}")

        if broker == "sinopac":
            console.print(
                '\nFormat:\n'
                '{\n'
                '  "sinopac": {\n'
                '    "api_key": "YOUR_API_KEY",\n'
                '    "secret_key": "YOUR_SECRET_KEY",\n'
                '    "ca_path": "C:/path/to/Sinopac.pfx",\n'
                '    "ca_password": "YOUR_ID_NUMBER"\n'
                '  }\n'
                '}'
            )
            console.print(
                "\n[bold]How to get API access:[/bold]\n"
                "  1. Visit SinoPac branch to sign API risk disclosure\n"
                "  2. Apply for API Key at https://www.sinotrade.com.tw\n"
                "  3. Download Sinopac.pfx certificate\n"
                "  4. Docs: https://sinotrade.github.io/"
            )
        elif broker == "fubon":
            console.print(
                '\nFormat:\n'
                '{\n'
                '  "fubon": {\n'
                '    "user_id": "YOUR_USER_ID",\n'
                '    "password": "YOUR_PASSWORD",\n'
                '    "pfx_path": "C:/path/to/fubon_cert.pfx",\n'
                '    "pfx_password": "YOUR_PFX_PASSWORD"\n'
                '  }\n'
                '}'
            )
            console.print(
                "\n[bold]How to get API access:[/bold]\n"
                "  1. Apply at https://www.fbs.com.tw/TradeAPI/\n"
                "  2. Download certificate via CATool\n"
                "  3. Download fubon_neo .whl and install\n"
                "  4. Docs: https://www.fbs.com.tw/TradeAPI/en/docs/"
            )
