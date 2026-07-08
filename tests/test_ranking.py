"""rankings table: add_ranking canonicalization, latest_rankings direction,
ticker_history ordering, invalid method rejection.
"""

import pytest

from portfoliodb.services.ranking_service import (
    add_ranking, list_rankings, latest_rankings, ticker_history,
)


class TestAddRanking:
    def test_invalid_method_rejected(self, tmp_db):
        with pytest.raises(ValueError, match="Invalid method"):
            add_ranking("NVDA", "not_a_method", "2026-07-06", 0.85)

    def test_non_iso_date_rejected(self, tmp_db):
        with pytest.raises(ValueError, match="Invalid score_date"):
            add_ranking("NVDA", "kelly", "07/06/2026", 0.85)

    def test_duplicate_ticker_method_date_rejected(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        with pytest.raises(ValueError, match="already exists"):
            add_ranking("NVDA", "kelly", "2026-07-06", 0.10)

    def test_same_ticker_different_date_is_allowed(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-06-01", 0.10)
        r = add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        assert r.headline_score == 0.85

    def test_weight_pct_out_of_range_rejected(self, tmp_db):
        with pytest.raises(ValueError, match="weight_pct must be between"):
            add_ranking("NVDA", "kelly", "2026-07-06", 0.85, weight_pct=-999)

    def test_bare_tw_digit_ticker_requires_market_hint(self, tmp_db):
        with pytest.raises(ValueError, match="Cannot canonicalise"):
            add_ranking("8299", "kelly", "2026-07-06", 0.5)

    def test_bare_tw_digit_ticker_with_market_hint_gets_suffixed(self, tmp_db):
        r = add_ranking("2330", "peg", "2026-07-05", 0.61, market_hint="TW")
        assert r.ticker == "2330.TW"

    def test_us_ticker_passes_through(self, tmp_db):
        r = add_ranking("nvda", "kelly", "2026-07-06", 0.85, weight_pct=21, source="7/6 投研 session")
        assert r.ticker == "NVDA"
        assert r.weight_pct == 21
        assert r.source == "7/6 投研 session"

    def test_method_version_is_optional_and_defaults_to_none(self, tmp_db):
        r = add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        assert r.method_version is None

    def test_method_version_round_trips(self, tmp_db):
        r = add_ranking("NVDA", "kelly", "2026-07-06", 0.85, method_version="V1.1")
        assert r.method_version == "V1.1"

    def test_method_version_whitespace_only_normalises_to_none(self, tmp_db):
        r = add_ranking("NVDA", "kelly", "2026-07-06", 0.85, method_version="   ")
        assert r.method_version is None

    def test_method_version_not_part_of_unique_key(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85, method_version="V1.1")
        with pytest.raises(ValueError, match="already exists"):
            add_ranking("NVDA", "kelly", "2026-07-06", 0.90, method_version="V2")


class TestLatestRankings:
    def test_peg_sorts_ascending_lower_is_better(self, tmp_db):
        add_ranking("NVDA", "peg", "2026-07-05", 0.33)
        add_ranking("MU", "peg", "2026-07-05", 0.06)
        add_ranking("2330.TW", "peg", "2026-07-05", 0.61)

        rows = latest_rankings("peg")
        assert [r.ticker for r in rows] == ["MU", "NVDA", "2330.TW"]

    def test_kelly_sorts_descending_higher_is_better(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        add_ranking("MU", "kelly", "2026-07-06", 0.56)
        add_ranking("2330.TW", "kelly", "2026-07-06", 0.75)

        rows = latest_rankings("kelly")
        assert [r.ticker for r in rows] == ["NVDA", "2330.TW", "MU"]

    def test_only_most_recent_snapshot_per_ticker_used(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-06-01", 0.10)
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85)

        rows = latest_rankings("kelly")
        assert len(rows) == 1
        assert rows[0].score_date == "2026-07-06"
        assert rows[0].headline_score == 0.85

    def test_missing_score_sorts_last(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        add_ranking("GOOG", "kelly", "2026-07-06", None)

        rows = latest_rankings("kelly")
        assert [r.ticker for r in rows] == ["NVDA", "GOOG"]

    def test_invalid_method_rejected(self, tmp_db):
        with pytest.raises(ValueError, match="Invalid method"):
            latest_rankings("not_a_method")


class TestListAndHistory:
    def test_list_rankings_filters_by_method_and_ticker(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        add_ranking("NVDA", "peg", "2026-07-05", 0.33)
        add_ranking("MU", "kelly", "2026-07-06", 0.56)

        assert len(list_rankings(method="kelly")) == 2
        assert len(list_rankings(ticker="NVDA")) == 2
        assert len(list_rankings(method="kelly", ticker="NVDA")) == 1

    def test_ticker_history_returns_all_methods_oldest_first(self, tmp_db):
        add_ranking("NVDA", "kelly", "2026-07-06", 0.85)
        add_ranking("NVDA", "peg", "2026-06-26", 0.33)

        rows = ticker_history("NVDA")
        assert [r.score_date for r in rows] == ["2026-06-26", "2026-07-06"]

    def test_ticker_history_canonicalises_lookup_key(self, tmp_db):
        add_ranking("2330", "peg", "2026-07-05", 0.61, market_hint="TW")
        rows = ticker_history("2330.TW")
        assert len(rows) == 1
