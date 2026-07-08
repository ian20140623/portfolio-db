"""Migration 002 — hardens the `rankings` table shape on existing DBs.

Background (2026-07-08):
  * `rankings` shipped in two rounds on this machine: round 1 had no
    UNIQUE(ticker, method, score_date) constraint (added by hand via
    drop+rebuild after Eagle Eye/Spock caught duplicate-row corruption in
    latest_rankings()); round 2 added `method_version` (added by hand via
    ALTER TABLE ADD COLUMN).
  * portfolio-db is a **single-machine, per-machine DB** — Air/NB never see
    this Mac mini's local schema fixes. `db.init_db()`'s
    `CREATE TABLE IF NOT EXISTS rankings (...)` is a silent no-op on any
    machine where `rankings` already exists from an earlier pull, so a
    machine that ran `rank add` before this migration existed would hard-
    crash on the next `rank add` after pulling this code (missing column /
    missing constraint), with no clue why (Eagle Eye, 2026-07-08 follow-up).

This script is idempotent and safe to run on any of the three shapes a
machine's local `rankings` table can be in:
  A. Table doesn't exist yet          -> no-op (init_db() will create it fresh).
  B. Table exists, already hardened   -> no-op.
  C. Table exists, missing constraint and/or method_version column -> fixed:
       1. If UNIQUE(ticker, method, score_date) is missing, rebuild the
          table (SQLite can't ALTER TABLE to add a multi-column UNIQUE).
          Duplicate (ticker, method, score_date) groups from the
          pre-constraint era are deduped, keeping the highest-id (most
          recently inserted) row per group; dropped rows are logged.
       2. If `method_version` is missing, ALTER TABLE ADD COLUMN (this one
          *is* safe as a plain ALTER — no constraint involved).

Invocation:
    python -m portfoliodb.migrations.m002_rankings_schema_hardening            # dry-run
    python -m portfoliodb.migrations.m002_rankings_schema_hardening --apply    # write

Before running --apply against a real (non-tmp_db-test) database, run
`python -m portfoliodb backup` first — the UNIQUE-missing branch rebuilds the
table (rename+recreate+copy), and while it's been tested against every shape
this migration expects, a fresh cold-backup snapshot costs one command and
means a bad surprise is a restore, not a loss (Eagle Eye, 2026-07-08
follow-up review — this migration's own review process is what surfaced the
need: real --apply runs happened against this machine's DB mid-development
without one).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys

from portfoliodb import db as _db_mod
from portfoliodb.db import APP_DIR, get_connection

LOG_PATH = APP_DIR / "migration_002.log"

TARGET_UNIQUE_COLUMNS = ("ticker", "method", "score_date")


def _log_lines(lines: list[str]) -> None:
    """Append a timestamped run record, including which DB file was targeted.

    The DB path is read live off `db.DB_PATH` (not imported by name) so a
    log entry always attributes itself correctly even under test monkeypatch
    — Spock's 2026-07-08 follow-up review: without this, a contaminated
    test/dev run and a real production run are indistinguishable after the
    fact (this file was fully polluted with synthetic test entries once,
    with no way to tell from the log alone).
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"\n===== migration_002 run @ {stamp} db={_db_mod.DB_PATH} =====\n")
        for line in lines:
            fh.write(line + "\n")


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _has_unique_constraint(conn) -> bool:
    """True if some index on `rankings` enforces UNIQUE(ticker, method, score_date)."""
    for idx in conn.execute("PRAGMA index_list(rankings)").fetchall():
        if not idx["unique"]:
            continue
        cols = [r["name"] for r in conn.execute(f"PRAGMA index_info({idx['name']})").fetchall()]
        if set(cols) == set(TARGET_UNIQUE_COLUMNS):
            return True
    return False


def _has_method_version_column(conn) -> bool:
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(rankings)").fetchall()]
    return "method_version" in cols


def _find_duplicate_groups(conn) -> list[dict]:
    """Rows sharing (ticker, method, score_date) — pre-constraint duplicates."""
    return [
        dict(r) for r in conn.execute(
            "SELECT ticker, method, score_date, COUNT(*) AS c, "
            "GROUP_CONCAT(id) AS ids "
            "FROM rankings GROUP BY ticker, method, score_date HAVING c > 1"
        ).fetchall()
    ]


def _rebuild_with_unique_constraint(conn, has_method_version: bool, apply: bool) -> list[str]:
    """Drop+recreate `rankings` with the UNIQUE constraint, deduping in place.

    Keeps the highest-id row per (ticker, method, score_date) group — that's
    the most recently inserted snapshot, treated as the authoritative one.
    """
    log: list[str] = []
    dup_groups = _find_duplicate_groups(conn)
    for g in dup_groups:
        ids = sorted(int(i) for i in g["ids"].split(","))
        keep, drop = ids[-1], ids[:-1]
        log.append(
            f"  DEDUP {g['ticker']}/{g['method']}/{g['score_date']}: "
            f"keeping id={keep}, dropping id(s)={drop}"
        )

    if not apply:
        return log

    # The rebuilt table always gets method_version — it's part of the target
    # schema regardless of whether *this* migration is the one adding it.
    # `has_method_version` only controls whether the copy can SELECT it from
    # the old table (old table may predate the column entirely).
    conn.executescript("""
        ALTER TABLE rankings RENAME TO rankings_pre_m002;
        CREATE TABLE rankings (
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
    """)
    new_cols = "id, ticker, method, method_version, score_date, headline_score, weight_pct, source, notes, created_at"
    old_cols = "id, ticker, method, " + ("method_version, " if has_method_version else "NULL, ") + \
               "score_date, headline_score, weight_pct, source, notes, created_at"
    conn.execute(f"""
        INSERT INTO rankings ({new_cols})
        SELECT {old_cols} FROM rankings_pre_m002
        WHERE id IN (
            SELECT MAX(id) FROM rankings_pre_m002
            GROUP BY ticker, method, score_date
        )
    """)
    conn.execute("DROP TABLE rankings_pre_m002")
    return log


def run(apply: bool) -> int:
    print(f"[migration_002] mode={'APPLY' if apply else 'DRY-RUN'}")
    log_lines: list[str] = [f"mode={'apply' if apply else 'dry-run'}"]

    with get_connection() as conn:
        if not _table_exists(conn, "rankings"):
            print("[migration_002] `rankings` table doesn't exist yet — nothing to do "
                  "(init_db() will create it fresh with the correct shape).")
            return 0

        needs_unique = not _has_unique_constraint(conn)
        needs_version_col = not _has_method_version_column(conn)

        if not needs_unique and not needs_version_col:
            print("[migration_002] `rankings` already has UNIQUE constraint + "
                  "method_version column — nothing to do.")
            return 0

        print(f"[migration_002] needs_unique_constraint={needs_unique}  "
              f"needs_method_version_column={needs_version_col}")

        if needs_unique:
            # Rebuild handles both problems at once if method_version is also
            # missing, so we don't ALTER-then-rebuild redundantly.
            dedup_log = _rebuild_with_unique_constraint(
                conn, has_method_version=not needs_version_col, apply=apply
            )
            log_lines.extend(dedup_log)
            for line in dedup_log:
                print(line)
            if apply and needs_version_col:
                needs_version_col = False  # rebuild already added the column
        elif needs_version_col:
            if apply:
                conn.execute("ALTER TABLE rankings ADD COLUMN method_version TEXT")
                log_lines.append("  ALTER TABLE rankings ADD COLUMN method_version TEXT")
                print("  ALTER TABLE rankings ADD COLUMN method_version TEXT")
            else:
                print("  (dry-run: would run ALTER TABLE rankings ADD COLUMN method_version TEXT)")

        if not apply:
            conn.rollback()

    if apply:
        _log_lines(log_lines)
        print(f"[migration_002] applied. log -> {LOG_PATH}")
    else:
        print("[migration_002] dry-run complete. re-run with --apply to write.")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Harden `rankings` table shape on existing DBs.")
    p.add_argument("--apply", action="store_true",
                   help="Actually write changes (default is dry-run).")
    args = p.parse_args(argv)
    return run(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
