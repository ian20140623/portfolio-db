"""Tests for the off-machine cold-backup module.

backup.py binds DB_PATH at import time and resolves the destination via the
PORTFOLIODB_BACKUP_DIR env var, so we patch `backup.DB_PATH` directly and point
the env var at tmp_path. `_timestamp` is patched to deterministic values so
rotation order is exercised without sleeping on real wall-clock seconds.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from portfoliodb import backup as bk


def _make_db(path: Path, rows: int = 3) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t(v) VALUES(?)", [(str(i),) for i in range(rows)])
    conn.commit()
    conn.close()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Source DB + redirected backup dir; returns (src_db, backup_dir)."""
    src = tmp_path / "portfolio.db"
    bdir = tmp_path / "db_backups"
    monkeypatch.setattr(bk, "DB_PATH", src)
    monkeypatch.setenv("PORTFOLIODB_BACKUP_DIR", str(bdir))
    return src, bdir


def _stamp_sequence(monkeypatch, *stamps):
    it = iter(stamps)
    monkeypatch.setattr(bk, "_timestamp", lambda: next(it))


def test_no_db_is_clean_noop(env):
    # DB does not exist yet -> None, not an error (scheduled run before rebuild).
    assert bk.create_backup() is None
    assert bk.list_backups() == []


def test_create_produces_verified_snapshot(env, monkeypatch):
    src, bdir = env
    _make_db(src)
    _stamp_sequence(monkeypatch, "20260618-000001")
    out = bk.create_backup()
    assert out is not None and out.exists()
    assert out.name == "portfolio-20260618-000001.db"
    # snapshot is a real, intact SQLite DB carrying the data
    n = sqlite3.connect(out).execute("SELECT COUNT(*) FROM t").fetchone()[0]
    assert n == 3
    bk._verify_integrity(out)  # must not raise


def test_atomic_publish_leaves_no_tmp(env, monkeypatch):
    src, bdir = env
    _make_db(src)
    _stamp_sequence(monkeypatch, "20260618-000001")
    bk.create_backup()
    assert list(bdir.glob("*.db.tmp")) == []


def test_rotation_keeps_newest(env, monkeypatch):
    src, bdir = env
    _make_db(src)
    _stamp_sequence(
        monkeypatch,
        "20260618-000001", "20260618-000002", "20260618-000003",
    )
    bk.create_backup(keep=2)
    bk.create_backup(keep=2)
    third = bk.create_backup(keep=2)
    remaining = bk.list_backups()
    assert [p.name for p in remaining] == [
        "portfolio-20260618-000003.db",
        "portfolio-20260618-000002.db",
    ]
    assert remaining[0] == third
    assert not (bdir / "portfolio-20260618-000001.db").exists()


def test_rotation_sweeps_stale_tmp(env, monkeypatch):
    src, bdir = env
    _make_db(src)
    bdir.mkdir(parents=True)
    leftover = bdir / "portfolio-old.db.tmp"
    leftover.write_bytes(b"junk")
    _stamp_sequence(monkeypatch, "20260618-000001")
    bk.create_backup()
    assert not leftover.exists()


def test_restore_into_fresh_target(env, monkeypatch, tmp_path):
    src, bdir = env
    _make_db(src)
    _stamp_sequence(monkeypatch, "20260618-000001")
    snap = bk.create_backup()

    target = tmp_path / "restored.db"
    monkeypatch.setattr(bk, "DB_PATH", target)
    dest = bk.restore_backup(snap)
    assert dest == target
    n = sqlite3.connect(target).execute("SELECT COUNT(*) FROM t").fetchone()[0]
    assert n == 3


def test_restore_refuses_overwrite_without_force(env, monkeypatch, tmp_path):
    src, bdir = env
    _make_db(src)
    _stamp_sequence(monkeypatch, "20260618-000001")
    snap = bk.create_backup()

    target = tmp_path / "live.db"
    _make_db(target, rows=99)
    monkeypatch.setattr(bk, "DB_PATH", target)
    with pytest.raises(FileExistsError):
        bk.restore_backup(snap)
    # untouched
    n = sqlite3.connect(target).execute("SELECT COUNT(*) FROM t").fetchone()[0]
    assert n == 99


def test_force_restore_makes_pre_restore_copy(env, monkeypatch, tmp_path):
    src, bdir = env
    _make_db(src, rows=3)
    _stamp_sequence(monkeypatch, "20260618-000001", "20260618-000002")
    snap = bk.create_backup()

    target = tmp_path / "live.db"
    _make_db(target, rows=99)
    monkeypatch.setattr(bk, "DB_PATH", target)
    bk.restore_backup(snap, force=True)

    # live DB now has the 3-row snapshot
    assert sqlite3.connect(target).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3
    # the old 99-row DB was preserved as a pre-restore safety copy
    safety = list(tmp_path.glob("portfolio.pre-restore-*.db"))
    assert len(safety) == 1
    assert sqlite3.connect(safety[0]).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 99


def test_restore_rejects_corrupt_snapshot(env, monkeypatch, tmp_path):
    src, bdir = env
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"definitely not sqlite")
    target = tmp_path / "live.db"
    monkeypatch.setattr(bk, "DB_PATH", target)
    with pytest.raises(sqlite3.DatabaseError):
        bk.restore_backup(bad, force=True)
    assert not target.exists()


def test_missing_snapshot_path_raises(env, monkeypatch, tmp_path):
    with pytest.raises(FileNotFoundError):
        bk.restore_backup(tmp_path / "nope.db")
