"""Database connection management and schema initialization."""

import platform
import sqlite3
from pathlib import Path
from contextlib import contextmanager


def _app_dir() -> Path:
    """Per-OS app data directory (outside cloud sync to avoid SQLite corruption)."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "PortfolioDB"
    if system == "Windows":
        return Path.home() / "AppData" / "Local" / "PortfolioDB"
    return Path.home() / ".local" / "share" / "PortfolioDB"


APP_DIR = _app_dir()
DB_DIR = APP_DIR
DB_PATH = APP_DIR / "portfolio.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    display_name TEXT   NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- legal_owner_id  = 法律名義人（戶頭掛誰名下）
-- economic_owner_id = 實際擁有人（誰的錢、誰承擔損益）
-- 兩者通常相同；不同時用於「戶頭借名」情境（e.g. 父親名下實際是兒子的錢）
CREATE TABLE IF NOT EXISTS accounts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    legal_owner_id    INTEGER NOT NULL REFERENCES users(id),
    economic_owner_id INTEGER NOT NULL REFERENCES users(id),
    account_name      TEXT    NOT NULL,
    broker            TEXT    NOT NULL,
    market            TEXT    NOT NULL,  -- TW, US, SG
    currency          TEXT    NOT NULL,  -- TWD, USD, SGD
    account_type      TEXT    NOT NULL DEFAULT 'brokerage',
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(legal_owner_id, account_name)
);

CREATE TABLE IF NOT EXISTS holdings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    ticker      TEXT    NOT NULL,
    shares      REAL    NOT NULL DEFAULT 0,
    avg_cost    REAL    NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, ticker)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    ticker      TEXT    NOT NULL,
    action      TEXT    NOT NULL,  -- BUY or SELL
    shares      REAL    NOT NULL,
    price       REAL    NOT NULL,
    fee         REAL    NOT NULL DEFAULT 0,
    tax         REAL    NOT NULL DEFAULT 0,
    currency    TEXT    NOT NULL,
    notes       TEXT,
    executed_at TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cash_positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    currency    TEXT    NOT NULL,
    balance     REAL    NOT NULL DEFAULT 0,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, currency)
);

CREATE TABLE IF NOT EXISTS cash_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    currency    TEXT    NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    description TEXT,
    executed_at TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS planned_orders (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id            INTEGER NOT NULL REFERENCES accounts(id),
    ticker                TEXT    NOT NULL,
    action                TEXT    NOT NULL,  -- BUY or SELL
    shares                REAL    NOT NULL,
    target_price          REAL,
    reason                TEXT,
    priority              TEXT    NOT NULL DEFAULT 'NORMAL',
    status                TEXT    NOT NULL DEFAULT 'PENDING',
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    executed_at           TEXT,
    linked_transaction_id INTEGER REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_currency TEXT    NOT NULL,
    to_currency   TEXT    NOT NULL,
    rate          REAL    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'yahoo',
    fetched_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_currency, to_currency)
);

CREATE TABLE IF NOT EXISTS price_cache (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT    NOT NULL UNIQUE,
    price      REAL    NOT NULL,
    currency   TEXT    NOT NULL,
    fetched_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Two-layer ticker identity (since 2026-05-26):
--   companies  = issuer layer (e.g. TSMC). Used for issuer aggregation only.
--   instruments= security layer (e.g. TSMC_TW_COMMON vs TSMC_US_ADR). The
--                `ticker` column is the canonical instrument key joined into
--                holdings/transactions/planned_orders/price_cache.
-- ADR and the underlying common share share company_id but are distinct
-- instruments: different market, currency, price, trading unit and P&L.
CREATE TABLE IF NOT EXISTS companies (
    company_id    TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS instruments (
    instrument_id TEXT PRIMARY KEY,
    ticker        TEXT NOT NULL UNIQUE,
    market        TEXT NOT NULL,
    currency      TEXT NOT NULL,
    company_id    TEXT,
    security_type TEXT,
    notes         TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS company_aliases (
    alias       TEXT NOT NULL,
    company_id  TEXT NOT NULL,
    kind        TEXT,
    UNIQUE(alias, company_id),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- Individual-stock ranking snapshots (since 2026-07-08). One row per
-- (ticker, method, score_date) — captures whichever scoring methodology
-- produced the number, so Sir's PEG / Kelly f* / 15-point framework work
-- stops living only in scratch notes and log entries.
-- NOTE for future schema edits: this table's shape is duplicated inline in
-- migrations/m002_rankings_schema_hardening.py's rebuild DDL (SQLite can't
-- ALTER TABLE to add a multi-column UNIQUE, so an existing per-machine DB on
-- an older shape needs a real rename+recreate, not just CREATE IF NOT
-- EXISTS). If you change columns/constraints here, check whether m002's
-- rebuild path also needs updating (Spock, 2026-07-08 follow-up review).
--   headline_score:  the single comparable number for the method
--                    (PEG ratio / Kelly f* / 15-point total, 3-15).
--   weight_pct:      suggested portfolio weight if the method produced one
--                    (mainly Kelly's normalised f*); NULL otherwise.
--   method_version:  free-text tag for which iteration of the methodology
--                    produced this score (e.g. "V1", "V1.1"). The framework
--                    itself is still evolving (scratch/20260527-投組初步想法.md
--                    is a living doc, not a frozen spec) — this lets later
--                    analysis tell "scored under the old rules" apart from
--                    "scored under the new rules" instead of silently
--                    conflating them. Nullable: not every snapshot needs one.
-- Direction (lower vs higher is better) is method-dependent and lives in
-- utils/constants.RANKING_DIRECTION, not in this table.
-- UNIQUE(ticker, method, score_date): a re-score on the same day is a
-- correction, not a second data point — add_ranking() rejects the
-- collision rather than silently duplicating the snapshot (2026-07-08,
-- Eagle Eye + Spock both caught duplicate rows corrupting latest_rankings()).
-- method_version is deliberately excluded from that key: latest_rankings()
-- assumes at most one row per (ticker, method, score_date), and folding
-- version into the key would reopen the same-day-duplicate class this
-- constraint exists to close, just gated on "different version" instead of
-- "literal duplicate" (Spock, 2026-07-08 follow-up review).
-- Note: method_version was added via `ALTER TABLE ... ADD COLUMN` on the
-- already-deployed prod table, so its physical column position there is
-- last (after created_at), not third as declared below — harmless since
-- every read/write in this codebase goes by column name, never position,
-- but worth knowing before "fixing" the declared order for cosmetic reasons.
CREATE TABLE IF NOT EXISTS rankings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,
    method         TEXT    NOT NULL,
    method_version TEXT,
    score_date     TEXT    NOT NULL,
    headline_score REAL,
    weight_pct     REAL,
    source         TEXT,
    notes          TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, method, score_date)
);
"""


@contextmanager
def get_connection():
    """Get a database connection with auto-commit/rollback.

    Usage:
        with get_connection() as conn:
            conn.execute("INSERT INTO ...")
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the database directory and all tables."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
