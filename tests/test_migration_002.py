"""Migration 002 — rankings table hardening on existing per-machine DBs.

Covers the gap Eagle Eye caught (2026-07-08): `rankings` shipped its UNIQUE
constraint and method_version column via hand-run ALTER/rebuild on one
machine only. Any other machine whose local DB already has an older-shaped
`rankings` table would hard-crash on the next `rank add` after pulling this
code, since `init_db()`'s CREATE TABLE IF NOT EXISTS is a silent no-op.
"""

import sqlite3

import pytest

from portfoliodb.migrations import m002_rankings_schema_hardening as m002


def _exec(db_path, sql, params=()):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(sql, params)
        conn.commit()


def _query(db_path, sql, params=()):
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _downgrade_to_round1_shape(db_path):
    """Simulate a machine that pulled round-1 code: no UNIQUE, no method_version."""
    _exec(db_path, "DROP TABLE rankings")
    _exec(db_path, """
        CREATE TABLE rankings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker         TEXT    NOT NULL,
            method         TEXT    NOT NULL,
            score_date     TEXT    NOT NULL,
            headline_score REAL,
            weight_pct     REAL,
            source         TEXT,
            notes          TEXT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _downgrade_to_pre_version_shape(db_path):
    """Simulate a machine that already has the UNIQUE constraint but not method_version."""
    _exec(db_path, "DROP TABLE rankings")
    _exec(db_path, """
        CREATE TABLE rankings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker         TEXT    NOT NULL,
            method         TEXT    NOT NULL,
            score_date     TEXT    NOT NULL,
            headline_score REAL,
            weight_pct     REAL,
            source         TEXT,
            notes          TEXT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(ticker, method, score_date)
        )
    """)


class TestFreshInstall:
    def test_noop_when_table_already_hardened(self, tmp_db):
        """tmp_db's init_db() already creates the final shape — migration is a no-op."""
        result = m002.run(apply=True)
        assert result == 0
        rows = _query(tmp_db, "SELECT * FROM rankings")
        assert rows == []  # untouched, still empty

    def test_noop_when_table_does_not_exist(self, tmp_db):
        _exec(tmp_db, "DROP TABLE rankings")
        result = m002.run(apply=True)
        assert result == 0


class TestRound1Shape:
    """No UNIQUE constraint, no method_version column — the worst case."""

    def test_adds_unique_constraint(self, tmp_db):
        _downgrade_to_round1_shape(tmp_db)
        m002.run(apply=True)

        with sqlite3.connect(str(tmp_db)) as conn:
            conn.row_factory = sqlite3.Row
            indexes = conn.execute("PRAGMA index_list(rankings)").fetchall()
            assert any(i["unique"] for i in indexes)

    def test_adds_method_version_column(self, tmp_db):
        _downgrade_to_round1_shape(tmp_db)
        m002.run(apply=True)

        with sqlite3.connect(str(tmp_db)) as conn:
            conn.row_factory = sqlite3.Row
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(rankings)").fetchall()]
            assert "method_version" in cols

    def test_preserves_non_duplicate_rows(self, tmp_db):
        _downgrade_to_round1_shape(tmp_db)
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('NVDA', 'kelly', '2026-07-06', 0.85)")
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('MU', 'peg', '2026-07-05', 0.06)")

        m002.run(apply=True)

        rows = _query(tmp_db, "SELECT ticker, method, headline_score FROM rankings ORDER BY ticker")
        assert len(rows) == 2
        assert rows[0]["ticker"] == "MU"
        assert rows[1]["ticker"] == "NVDA"

    def test_dedupes_keeping_highest_id_per_group(self, tmp_db):
        """Pre-constraint duplicate (ticker, method, score_date) — keep the most recent."""
        _downgrade_to_round1_shape(tmp_db)
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('MU', 'kelly', '2026-07-06', 0.56)")
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('MU', 'kelly', '2026-07-06', 0.60)")  # accidental re-run, higher id

        m002.run(apply=True)

        rows = _query(tmp_db, "SELECT ticker, headline_score FROM rankings WHERE ticker = 'MU'")
        assert len(rows) == 1
        assert rows[0]["headline_score"] == 0.60  # the later insert wins

    def test_dry_run_makes_no_changes(self, tmp_db):
        _downgrade_to_round1_shape(tmp_db)
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('NVDA', 'kelly', '2026-07-06', 0.85)")

        m002.run(apply=False)

        with sqlite3.connect(str(tmp_db)) as conn:
            conn.row_factory = sqlite3.Row
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(rankings)").fetchall()]
            assert "method_version" not in cols  # unchanged
            indexes = conn.execute("PRAGMA index_list(rankings)").fetchall()
            assert not any(i["unique"] for i in indexes)  # unchanged
        rows = _query(tmp_db, "SELECT * FROM rankings")
        assert len(rows) == 1  # no dedup happened either

    def test_idempotent_second_run_is_noop(self, tmp_db):
        _downgrade_to_round1_shape(tmp_db)
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('NVDA', 'kelly', '2026-07-06', 0.85)")

        m002.run(apply=True)
        first_pass_rows = _query(tmp_db, "SELECT * FROM rankings")

        m002.run(apply=True)  # second run should no-op, not error
        second_pass_rows = _query(tmp_db, "SELECT * FROM rankings")

        assert first_pass_rows == second_pass_rows

    def test_add_ranking_works_after_migration(self, tmp_db):
        """The actual regression Eagle Eye reproduced: add_ranking() must not crash post-migration."""
        _downgrade_to_round1_shape(tmp_db)
        m002.run(apply=True)

        from portfoliodb.services.ranking_service import add_ranking
        r = add_ranking("NVDA", "kelly", "2026-07-06", 0.85, method_version="V1.1")
        assert r.method_version == "V1.1"


class TestPreVersionColumnShape:
    """UNIQUE constraint already present, only method_version missing."""

    def test_adds_column_without_touching_existing_rows(self, tmp_db):
        _downgrade_to_pre_version_shape(tmp_db)
        _exec(tmp_db,
              "INSERT INTO rankings (ticker, method, score_date, headline_score) "
              "VALUES ('NVDA', 'kelly', '2026-07-06', 0.85)")

        m002.run(apply=True)

        rows = _query(tmp_db, "SELECT ticker, method_version FROM rankings")
        assert len(rows) == 1
        assert rows[0]["ticker"] == "NVDA"
        assert rows[0]["method_version"] is None

    def test_unique_constraint_still_enforced_after_column_add(self, tmp_db):
        _downgrade_to_pre_version_shape(tmp_db)
        m002.run(apply=True)

        with pytest.raises(sqlite3.IntegrityError):
            _exec(tmp_db,
                  "INSERT INTO rankings (ticker, method, score_date, headline_score) "
                  "VALUES ('NVDA', 'kelly', '2026-07-06', 0.85)")
            _exec(tmp_db,
                  "INSERT INTO rankings (ticker, method, score_date, headline_score) "
                  "VALUES ('NVDA', 'kelly', '2026-07-06', 0.90)")
