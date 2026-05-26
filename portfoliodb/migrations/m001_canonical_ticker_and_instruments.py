"""Migration 001 — canonical ticker backfill + instrument / company seed.

Background (2026-05-26):
  * `order add` shipped a TW auto-suffix on 5/26 but only normalised future
    orders. Pre-existing rows ("2330", "2383" without ".TW") leak into
    review_orders and breakdown intent JOINs as ghost tickers.
  * Two-layer identity (instrument vs company) was missing entirely; the
    TSM (ADR) / 2330.TW (common share) case sits in production but the
    schema offered no way to express "same issuer, different security".

This script:
  1. Creates the companies / instruments / company_aliases tables if absent
     (idempotent CREATE IF NOT EXISTS via `db.init_db()`).
  2. Walks every ticker in holdings / transactions / planned_orders /
     price_cache, computes the canonical form via `canonical_ticker()`,
     and UPDATEs rows whose stored ticker is raw.
  3. Refuses to guess for ambiguous TW digit tickers (8/6/9 prefix) —
     they land on a manual-review list and the row is left untouched.
  4. Upserts an `instruments` row for every canonical ticker (provisional
     mapping until issuer linkage is added by hand or future migration).
  5. Seeds the TSMC company plus TSMC_TW_COMMON and TSMC_US_ADR instruments
     to demonstrate the two-layer model — these two stay distinct on the
     instrument layer.
  6. Writes a full audit trail to `<APP_DIR>/migration_001.log`.

Invocation:
    python -m portfoliodb.migrations.m001_canonical_ticker_and_instruments            # dry-run
    python -m portfoliodb.migrations.m001_canonical_ticker_and_instruments --apply    # write
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path
from typing import Iterable

from portfoliodb.db import APP_DIR, get_connection, init_db
from portfoliodb.utils.ticker import canonical_ticker

LOG_PATH = APP_DIR / "migration_001.log"

# Tables that hold a `ticker` column we want to backfill. For each we record
# the account-bearing column (or None for price_cache, which is global) so the
# script can derive a market hint per row.
TICKER_TABLES: list[tuple[str, str | None]] = [
    ("holdings", "account_id"),
    ("transactions", "account_id"),
    ("planned_orders", "account_id"),
    ("price_cache", None),
]

# Seed data — only TSMC this round (per Sir 2026-05-26 decision (b)).
SEED_COMPANIES = [
    ("TSMC", "台積電", "TSMC issuer demo — paired instruments below illustrate "
                       "ADR vs common share separation on the instrument layer."),
]

SEED_INSTRUMENTS = [
    # instrument_id,        ticker,    market, currency, company_id, type,     notes
    ("TSMC_TW_COMMON", "2330.TW", "TW", "TWD", "TSMC", "COMMON",
     "Taiwan listed common share."),
    ("TSMC_US_ADR",    "TSM",     "US", "USD", "TSMC", "ADR",
     "NYSE-listed ADR. Not interchangeable with 2330.TW for order / position / "
     "P&L purposes — different market, currency and trading unit."),
]

SEED_ALIASES = [
    ("台積電", "TSMC", "name_zh"),
    ("Taiwan Semiconductor", "TSMC", "name_en"),
    ("Taiwan Semiconductor Manufacturing", "TSMC", "name_en"),
    ("TSMC", "TSMC", "abbr"),
]


def _log_lines(lines: Iterable[str]) -> None:
    """Append lines to the migration log. Each invocation gets a timestamped header."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"\n===== migration_001 run @ {stamp} =====\n")
        for line in lines:
            fh.write(line + "\n")


def _scan_table(conn, table: str, account_col: str | None) -> list[dict]:
    """Return rows of (id, ticker, market_hint) for one ticker-bearing table."""
    if account_col:
        rows = conn.execute(
            f"SELECT t.id AS id, t.ticker AS ticker, a.market AS market "
            f"FROM {table} t LEFT JOIN accounts a ON t.{account_col} = a.id"
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT id, ticker, NULL AS market FROM {table}"
        ).fetchall()
    return [dict(r) for r in rows]


def _plan_table(rows: list[dict], table: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Split rows into (no_change, will_update, unresolved)."""
    no_change, will_update, unresolved = [], [], []
    for r in rows:
        raw = r["ticker"]
        try:
            canon, reason = canonical_ticker(raw, market_hint=r["market"])
        except ValueError as e:
            unresolved.append({**r, "table": table, "reason": f"invalid ticker: {e}"})
            continue
        if reason:
            unresolved.append({**r, "table": table, "reason": reason, "canonical": canon})
        elif canon != raw:
            will_update.append({**r, "table": table, "canonical": canon})
        else:
            no_change.append({**r, "table": table})
    return no_change, will_update, unresolved


def _apply_table_updates(conn, table: str, updates: list[dict]) -> list[str]:
    """Apply UPDATE statements row-by-row using the raw ticker as the match key.

    Row-level match (rather than blanket WHERE ticker=?) lets us be precise in
    the log and avoid surprising mass-updates if some other row happens to
    share the same raw string under a different market.
    """
    log_lines: list[str] = []
    for u in updates:
        conn.execute(
            f"UPDATE {table} SET ticker = ? WHERE id = ? AND ticker = ?",
            (u["canonical"], u["id"], u["ticker"]),
        )
        log_lines.append(
            f"  UPDATE {table} id={u['id']}: '{u['ticker']}' -> '{u['canonical']}'"
        )
    return log_lines


def _collect_distinct_canonicals(conn) -> dict[str, dict]:
    """Walk all 4 tables (post-backfill) and collect canonical tickers + market.

    Used to upsert provisional instruments rows. Market is derived from the
    suffix where possible (`.TW`/`.TWO` -> TW, `.SI` -> SG, else default per
    the owning account or US fallback).
    """
    from portfoliodb.utils.ticker import detect_market
    from portfoliodb.utils.constants import MARKET_CURRENCY
    seen: dict[str, dict] = {}
    for table, account_col in TICKER_TABLES:
        if account_col:
            rows = conn.execute(
                f"SELECT DISTINCT t.ticker AS ticker, a.market AS market, "
                f"       a.currency AS currency "
                f"FROM {table} t LEFT JOIN accounts a ON t.{account_col} = a.id"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT DISTINCT ticker, NULL AS market, currency FROM {table}"
            ).fetchall()
        for r in rows:
            t = r["ticker"]
            if t in seen:
                continue
            market = r["market"] or detect_market(t)
            currency = r["currency"] or MARKET_CURRENCY.get(market, "USD")
            seen[t] = {"ticker": t, "market": market, "currency": currency}
    return seen


def _upsert_instrument_provisional(
    conn, ticker: str, market: str, currency: str
) -> str | None:
    """Insert a provisional instruments row keyed by ticker, no-op if present.

    Provisional rows use the ticker itself as `instrument_id` and leave
    `company_id` NULL. The notes column records that the row is provisional
    so future inspection makes the status obvious.
    """
    existing = conn.execute(
        "SELECT instrument_id FROM instruments WHERE ticker = ?", (ticker,)
    ).fetchone()
    if existing:
        return None
    conn.execute(
        "INSERT INTO instruments "
        "(instrument_id, ticker, market, currency, company_id, security_type, notes) "
        "VALUES (?, ?, ?, ?, NULL, NULL, ?)",
        (ticker, ticker, market, currency,
         "provisional: instrument_id == ticker, awaiting issuer linkage"),
    )
    return f"  INSERT instrument provisional: {ticker} (market={market}, currency={currency})"


def _seed_tsmc(conn) -> list[str]:
    """Idempotent seed for the TSMC company + paired instruments + aliases."""
    out: list[str] = []
    for company_id, display_name, notes in SEED_COMPANIES:
        existing = conn.execute(
            "SELECT company_id FROM companies WHERE company_id = ?", (company_id,)
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO companies (company_id, display_name, notes) VALUES (?, ?, ?)",
            (company_id, display_name, notes),
        )
        out.append(f"  INSERT company: {company_id} ({display_name})")

    for inst_id, ticker, market, currency, company_id, sec_type, notes in SEED_INSTRUMENTS:
        # If a provisional row was created for this ticker earlier, upgrade it
        # in place rather than racing the UNIQUE(ticker) constraint.
        existing = conn.execute(
            "SELECT instrument_id, company_id FROM instruments WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if existing and existing["instrument_id"] == inst_id and existing["company_id"] == company_id:
            continue
        if existing:
            conn.execute(
                "UPDATE instruments SET instrument_id = ?, market = ?, currency = ?, "
                "       company_id = ?, security_type = ?, notes = ? "
                "WHERE ticker = ?",
                (inst_id, market, currency, company_id, sec_type, notes, ticker),
            )
            out.append(
                f"  UPGRADE instrument: ticker={ticker} -> "
                f"instrument_id={inst_id}, company_id={company_id}"
            )
        else:
            conn.execute(
                "INSERT INTO instruments "
                "(instrument_id, ticker, market, currency, company_id, security_type, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (inst_id, ticker, market, currency, company_id, sec_type, notes),
            )
            out.append(
                f"  INSERT instrument: {inst_id} (ticker={ticker}, "
                f"company_id={company_id}, type={sec_type})"
            )

    for alias, company_id, kind in SEED_ALIASES:
        existing = conn.execute(
            "SELECT 1 FROM company_aliases WHERE alias = ? AND company_id = ?",
            (alias, company_id),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO company_aliases (alias, company_id, kind) VALUES (?, ?, ?)",
            (alias, company_id, kind),
        )
        out.append(f"  INSERT company_alias: {alias} -> {company_id} ({kind})")
    return out


def _format_section(title: str, rows: list[dict], columns: tuple[str, ...]) -> str:
    if not rows:
        return f"{title}: (none)"
    out = [f"{title} ({len(rows)}):"]
    for r in rows:
        cells = "  ".join(f"{c}={r.get(c)}" for c in columns)
        out.append(f"  {cells}")
    return "\n".join(out)


def run(apply: bool) -> int:
    """Execute the migration. Returns 0 on success, 1 if unresolved tickers exist."""
    print(f"[migration_001] mode={'APPLY' if apply else 'DRY-RUN'}")
    init_db()  # creates new tables if absent (idempotent)

    log_lines: list[str] = [f"mode={'apply' if apply else 'dry-run'}"]
    all_unresolved: list[dict] = []
    total_updates = 0

    with get_connection() as conn:
        # 1. Backfill ticker columns table by table.
        for table, account_col in TICKER_TABLES:
            rows = _scan_table(conn, table, account_col)
            no_change, will_update, unresolved = _plan_table(rows, table)
            print(f"\n[{table}] total={len(rows)}  no_change={len(no_change)}  "
                  f"will_update={len(will_update)}  unresolved={len(unresolved)}")
            print(_format_section(
                f"  will_update[{table}]", will_update,
                ("id", "ticker", "canonical", "market"),
            ))
            if unresolved:
                print(_format_section(
                    f"  unresolved[{table}]", unresolved,
                    ("id", "ticker", "market", "reason"),
                ))
            all_unresolved.extend(unresolved)

            if apply and will_update:
                log_lines.extend(_apply_table_updates(conn, table, will_update))
                total_updates += len(will_update)

        # 2. Upsert provisional instruments + seed TSMC.
        canonicals = _collect_distinct_canonicals(conn)
        print(f"\n[instruments] distinct canonical tickers post-backfill: {len(canonicals)}")
        if apply:
            for info in canonicals.values():
                line = _upsert_instrument_provisional(
                    conn, info["ticker"], info["market"], info["currency"]
                )
                if line:
                    log_lines.append(line)
            seed_lines = _seed_tsmc(conn)
            log_lines.extend(seed_lines)
            for line in seed_lines:
                print(line)
        else:
            print("  (dry-run: would upsert provisional rows and seed TSMC)")

        if not apply:
            conn.rollback()

    if all_unresolved:
        print("\n=== manual-review list ===")
        for u in all_unresolved:
            print(f"  table={u['table']} id={u['id']} ticker={u['ticker']} reason={u['reason']}")
        log_lines.append(f"unresolved_count={len(all_unresolved)}")

    log_lines.append(f"total_updates={total_updates}")
    if apply:
        _log_lines(log_lines)
        print(f"\n[migration_001] applied. log -> {LOG_PATH}")
    else:
        print(f"\n[migration_001] dry-run complete. re-run with --apply to write.")

    return 1 if all_unresolved and apply else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Canonical ticker backfill + instrument seed.")
    p.add_argument("--apply", action="store_true",
                   help="Actually write changes (default is dry-run).")
    args = p.parse_args(argv)
    return run(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
