"""Shared pytest fixtures.

Tests run against an isolated SQLite file under a tmp dir — production DB at
`~/Library/Application Support/PortfolioDB/portfolio.db` is never touched.
We monkeypatch the module-level `DB_PATH` (and `APP_DIR` for the migration
log) before any service code opens a connection.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Provide a clean SQLite DB + APP_DIR redirected to tmp_path.

    Yields the path so tests can sqlite3-connect if they need direct SQL.
    Schema is initialised via the real `init_db()` so we test against the
    production DDL (including the new companies / instruments / aliases tables).
    """
    db_dir: Path = tmp_path / "PortfolioDB"
    db_dir.mkdir()
    db_path = db_dir / "portfolio.db"

    from portfoliodb import db as db_mod
    monkeypatch.setattr(db_mod, "APP_DIR", db_dir)
    monkeypatch.setattr(db_mod, "DB_DIR", db_dir)
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)

    # Migration modules cache APP_DIR / LOG_PATH at import — refresh both so
    # the log lands inside tmp_path rather than the real ~/Library path.
    from portfoliodb.migrations import m001_canonical_ticker_and_instruments as m001
    monkeypatch.setattr(m001, "LOG_PATH", db_dir / "migration_001.log")
    from portfoliodb.migrations import m002_rankings_schema_hardening as m002
    monkeypatch.setattr(m002, "LOG_PATH", db_dir / "migration_002.log")

    db_mod.init_db()
    yield db_path
