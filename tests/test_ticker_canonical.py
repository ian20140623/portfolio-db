"""Unit tests for canonical_ticker — the single normalisation source."""

import pytest

from portfoliodb.utils.ticker import canonical_ticker


class TestCanonicalTicker:
    def test_already_suffixed_tw_is_kept(self):
        assert canonical_ticker("2330.TW") == ("2330.TW", None)

    def test_already_suffixed_two_is_kept(self):
        assert canonical_ticker("8299.TWO") == ("8299.TWO", None)

    def test_already_suffixed_si_is_kept(self):
        assert canonical_ticker("D05.SI") == ("D05.SI", None)

    def test_tw_account_appends_tw_to_listed_digit_ticker(self):
        canon, reason = canonical_ticker("2330", market_hint="TW")
        assert canon == "2330.TW"
        assert reason is None

    def test_2383_under_tw_account_normalises_to_tw(self):
        canon, reason = canonical_ticker("2383", market_hint="TW")
        assert canon == "2383.TW"
        assert reason is None

    def test_8299_under_tw_is_unresolved_not_guessed(self):
        canon, reason = canonical_ticker("8299", market_hint="TW")
        assert canon == "8299"  # untouched, do not guess
        assert reason is not None
        assert "manual confirmation" in reason or "needs" in reason

    def test_6_prefix_tw_is_unresolved(self):
        canon, reason = canonical_ticker("6505", market_hint="TW")
        assert canon == "6505"
        assert reason is not None

    def test_us_letter_ticker_unchanged(self):
        assert canonical_ticker("TSM") == ("TSM", None)
        assert canonical_ticker("AAPL") == ("AAPL", None)

    def test_digit_ticker_without_market_hint_is_unresolved(self):
        canon, reason = canonical_ticker("2330")
        assert canon == "2330"
        assert reason is not None

    def test_lowercase_input_is_uppercased(self):
        assert canonical_ticker("aapl") == ("AAPL", None)

    def test_empty_ticker_raises(self):
        with pytest.raises(ValueError):
            canonical_ticker("")
        with pytest.raises(ValueError):
            canonical_ticker("   ")
