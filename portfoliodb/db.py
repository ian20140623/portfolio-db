"""Database connection management and schema initialization."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Store DB outside OneDrive to avoid sync corruption
DB_DIR = Path.home() / "AppData" / "Local" / "PortfolioDB"
DB_PATH = DB_DIR / "portfolio.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    display_name TEXT   NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    account_name TEXT    NOT NULL,
    broker       TEXT    NOT NULL,
    market       TEXT    NOT NULL,  -- TW, US, SG
    currency     TEXT    NOT NULL,  -- TWD, USD, SGD
    account_type TEXT    NOT NULL DEFAULT 'brokerage',
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, account_name)
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
