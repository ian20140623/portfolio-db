"""review_orders + breakdown intent: runtime canonical match.

Covers Sir's case 4 (repeated_tickers no longer split by suffix) and case 7
(ADR vs common share never merged on the instrument layer).
"""

import sqlite3

import pytest


def _exec(db_path, sql, params=()):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(sql, params)
        conn.commit()


@pytest.fixture()
def seeded_db(tmp_db):
    _exec(tmp_db,
          "INSERT INTO users (id, username, display_name) VALUES (1, 'ian', 'Ian')")
    _exec(tmp_db,
          "INSERT INTO accounts (id, legal_owner_id, economic_owner_id, "
          "account_name, broker, market, currency) "
          "VALUES (1, 1, 1, 'TW', 'fubon', 'TW', 'TWD')")
    _exec(tmp_db,
          "INSERT INTO accounts (id, legal_owner_id, economic_owner_id, "
          "account_name, broker, market, currency) "
          "VALUES (2, 1, 1, 'US', 'firstrade', 'US', 'USD')")
    return tmp_db


class TestReviewOrdersCanonical:
    def test_raw_and_suffixed_same_ticker_count_as_one_instrument(self, seeded_db):
        """Sir case 4: 2330 + 2330.TW must aggregate as one ticker in repeated_tickers."""
        _exec(seeded_db,
              "INSERT INTO planned_orders (account_id, ticker, action, shares, status) "
              "VALUES (1, '2330', 'BUY', 1000, 'CANCELLED')")
        _exec(seeded_db,
              "INSERT INTO planned_orders (account_id, ticker, action, shares, status) "
              "VALUES (1, '2330.TW', 'BUY', 1000, 'CANCELLED')")

        from portfoliodb.services.order_service import review_orders
        r = review_orders(since_days=365)
        repeated = dict(r["repeated_tickers"])
        assert repeated.get("2330.TW") == 2
        assert "2330" not in repeated  # raw form must not leak

    def test_adr_and_common_share_stay_distinct(self, seeded_db):
        """Sir case 7: TSM and 2330.TW are different instruments, must not merge."""
        _exec(seeded_db,
              "INSERT INTO planned_orders (account_id, ticker, action, shares, status) "
              "VALUES (1, '2330.TW', 'BUY', 1000, 'CANCELLED')")
        _exec(seeded_db,
              "INSERT INTO planned_orders (account_id, ticker, action, shares, status) "
              "VALUES (2, 'TSM', 'BUY', 100, 'CANCELLED')")

        from portfoliodb.services.order_service import review_orders
        r = review_orders(since_days=365)
        tickers_seen = {o["ticker"] for o in r["unexecuted"]}
        assert "2330.TW" in tickers_seen
        assert "TSM" in tickers_seen
        # Each one appears exactly once — they must NOT collapse via company alias.
        assert dict(r["repeated_tickers"]) == {}


class TestBreakdownPendingIntents:
    def test_pending_intent_join_key_is_canonical(self, seeded_db):
        """A PENDING order written as '2330' must show up under the canonical '2330.TW'."""
        _exec(seeded_db,
              "INSERT INTO planned_orders (account_id, ticker, action, shares, "
              "target_price, status) "
              "VALUES (1, '2330', 'BUY', 1000, 1180, 'PENDING')")
        _exec(seeded_db,
              "INSERT INTO holdings (account_id, ticker, shares, avg_cost) "
              "VALUES (1, '2330.TW', 5000, 580)")

        from portfoliodb.services.portfolio_service import get_family_breakdown
        result = get_family_breakdown(base_currency="TWD")
        intents = result["pending_intents"]
        assert "2330.TW" in intents
        assert any("加" in label and "1,000" in label for label in intents["2330.TW"])
        assert "2330" not in intents
