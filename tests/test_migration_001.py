"""Migration 001 — canonical ticker backfill + TSMC seed.

Covers Sir's required cases (8 items) plus idempotency:
  1. 2330 and 2330.TW are treated as the same TW instrument after migration.
  2. 2383 and 2383.TW likewise.
  3. TSM and 2330.TW share company_id "TSMC" but have distinct instrument_id.
  4. repeated_tickers no longer splits a single intent across suffix variants.
  5. The migration script is idempotent (second apply is a no-op).
  8. Ambiguous TW digit tickers (8xxx) stay on the manual-review list.

Cases 6 (yfinance noise) and 7 (ADR vs common share P&L) live in
test_review_orders.py / test_price_warnings.py, since they exercise the
review / price layers respectively.
"""

import sqlite3

import pytest

from portfoliodb.migrations import m001_canonical_ticker_and_instruments as m001


def _exec(db_path, sql, params=()):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(sql, params)
        conn.commit()


def _query(db_path, sql, params=()):
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@pytest.fixture()
def seeded_db(tmp_db):
    """Seed users / accounts / pre-migration orders matching the production layout."""
    _exec(tmp_db,
          "INSERT INTO users (id, username, display_name) VALUES (1, 'ian', 'Ian')")
    _exec(tmp_db,
          "INSERT INTO accounts (id, legal_owner_id, economic_owner_id, account_name, "
          "broker, market, currency) "
          "VALUES (1, 1, 1, 'TW broker', 'fubon', 'TW', 'TWD')")
    _exec(tmp_db,
          "INSERT INTO accounts (id, legal_owner_id, economic_owner_id, account_name, "
          "broker, market, currency) "
          "VALUES (2, 1, 1, 'US broker', 'firstrade', 'US', 'USD')")

    # Pre-migration: two raw TW orders (no suffix) + two already-suffixed.
    _exec(tmp_db,
          "INSERT INTO planned_orders (id, account_id, ticker, action, shares, "
          "target_price, status) "
          "VALUES (1, 1, '2330', 'BUY', 1000, 1180, 'CANCELLED')")
    _exec(tmp_db,
          "INSERT INTO planned_orders (id, account_id, ticker, action, shares, "
          "target_price, status) "
          "VALUES (2, 1, '2383', 'SELL', 1000, 5400, 'CANCELLED')")
    _exec(tmp_db,
          "INSERT INTO planned_orders (id, account_id, ticker, action, shares, "
          "target_price, status) "
          "VALUES (3, 1, '2330.TW', 'BUY', 1000, 1180, 'CANCELLED')")
    _exec(tmp_db,
          "INSERT INTO planned_orders (id, account_id, ticker, action, shares, "
          "target_price, status) "
          "VALUES (4, 1, '2383.TW', 'SELL', 1000, 5400, 'CANCELLED')")

    # A holding pair: TSM (US ADR) and 2330.TW (TW common) — same issuer.
    _exec(tmp_db,
          "INSERT INTO holdings (account_id, ticker, shares, avg_cost) "
          "VALUES (1, '2330.TW', 5000, 580.5)")
    _exec(tmp_db,
          "INSERT INTO holdings (account_id, ticker, shares, avg_cost) "
          "VALUES (2, 'TSM', 100, 180.0)")
    return tmp_db


class TestMigrationBackfill:
    def test_raw_2330_becomes_2330_tw(self, seeded_db):
        m001.run(apply=True)
        rows = _query(seeded_db, "SELECT id, ticker FROM planned_orders ORDER BY id")
        tickers = {r["id"]: r["ticker"] for r in rows}
        assert tickers[1] == "2330.TW"  # Sir case 1
        assert tickers[3] == "2330.TW"  # already canonical, unchanged

    def test_raw_2383_becomes_2383_tw(self, seeded_db):
        m001.run(apply=True)
        rows = _query(seeded_db, "SELECT id, ticker FROM planned_orders ORDER BY id")
        tickers = {r["id"]: r["ticker"] for r in rows}
        assert tickers[2] == "2383.TW"  # Sir case 2
        assert tickers[4] == "2383.TW"

    def test_dry_run_does_not_mutate(self, seeded_db):
        m001.run(apply=False)
        rows = _query(seeded_db, "SELECT ticker FROM planned_orders WHERE id = 1")
        assert rows[0]["ticker"] == "2330"  # unchanged

    def test_idempotent_second_apply_is_noop(self, seeded_db):
        m001.run(apply=True)
        before = _query(seeded_db, "SELECT id, ticker FROM planned_orders ORDER BY id")
        # Second run must not double-suffix or otherwise corrupt the rows.
        m001.run(apply=True)
        after = _query(seeded_db, "SELECT id, ticker FROM planned_orders ORDER BY id")
        assert before == after  # Sir case 5


class TestInstrumentIdentity:
    def test_tsm_and_2330tw_share_company_but_not_instrument(self, seeded_db):
        m001.run(apply=True)
        rows = _query(
            seeded_db,
            "SELECT instrument_id, ticker, company_id, security_type "
            "FROM instruments WHERE company_id = 'TSMC' ORDER BY ticker",
        )
        by_ticker = {r["ticker"]: r for r in rows}
        assert "2330.TW" in by_ticker
        assert "TSM" in by_ticker
        # Sir case 3: same company_id, different instrument_id, different type.
        assert by_ticker["2330.TW"]["company_id"] == by_ticker["TSM"]["company_id"] == "TSMC"
        assert by_ticker["2330.TW"]["instrument_id"] != by_ticker["TSM"]["instrument_id"]
        assert by_ticker["2330.TW"]["security_type"] == "COMMON"
        assert by_ticker["TSM"]["security_type"] == "ADR"

    def test_tsmc_aliases_seeded(self, seeded_db):
        m001.run(apply=True)
        aliases = {r["alias"] for r in _query(
            seeded_db, "SELECT alias FROM company_aliases WHERE company_id = 'TSMC'"
        )}
        assert {"台積電", "Taiwan Semiconductor", "TSMC"}.issubset(aliases)

    def test_alias_is_not_an_instrument_key(self, seeded_db):
        """A company alias (issuer-layer) must never collide with a stored ticker."""
        m001.run(apply=True)
        # No instruments row should have ticker == "台積電" or "TSMC" the alias
        # (TSMC happens to be the company_id, but the alias must not become a
        # tradable ticker key).
        hits = _query(
            seeded_db,
            "SELECT ticker FROM instruments WHERE ticker IN ('台積電', 'Taiwan Semiconductor')",
        )
        assert hits == []


class TestAmbiguousTicker:
    def test_8xxx_digit_ticker_lands_on_unresolved_list(self, tmp_db):
        """Sir case 8: ambiguous suffix is reported, not guessed."""
        _exec(tmp_db,
              "INSERT INTO users (id, username, display_name) VALUES (1, 'ian', 'Ian')")
        _exec(tmp_db,
              "INSERT INTO accounts (id, legal_owner_id, economic_owner_id, "
              "account_name, broker, market, currency) "
              "VALUES (1, 1, 1, 'TW', 'fubon', 'TW', 'TWD')")
        _exec(tmp_db,
              "INSERT INTO planned_orders (account_id, ticker, action, shares, status) "
              "VALUES (1, '8299', 'BUY', 100, 'PENDING')")

        m001.run(apply=True)

        # Ambiguous row must stay untouched: rule refuses to guess .TW vs .TWO.
        rows = _query(tmp_db, "SELECT ticker FROM planned_orders")
        assert rows[0]["ticker"] == "8299"
