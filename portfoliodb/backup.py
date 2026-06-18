"""Off-machine cold backup for portfolio.db.

Why this exists
---------------
portfolio.db lives in per-OS AppData *outside* any cloud-sync folder (see
``db._app_dir``) so that SQLite's live WAL files never fight bidirectional sync
and corrupt the database. That decision protects against corruption — but it
leaves **no off-machine copy at all**, so a full machine loss destroys the DB
outright (2026-06-14: the Mac mini master was reformatted; the local DB and its
migration snapshots were gone, no Time Machine, no Dropbox copy).

This module closes that gap *without* reintroducing the corruption risk. The
SQLite online-backup API produces a single consistent snapshot with no WAL
involvement; we write that snapshot into Dropbox as a plain **cold** file that is
never opened live — one-way, write-then-leave-alone — which is safe to sync.

Design notes
------------
- Snapshot is built into a ``.tmp`` in the destination dir, integrity-checked,
  then atomically ``rename``-published so Dropbox never uploads a half-written DB.
- Filenames sort lexicographically == chronologically (``portfolio-YYYYmmdd-HHMMSS.db``)
  so rotation is a simple name sort.
- No silent workaround: integrity / empty-file failures raise, they do not return
  a "successful" bad backup.
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from portfoliodb.db import DB_PATH

# Master is the Mac mini; Dropbox cold-backup target lives next to the synced
# family-wealth memory under PJHub/portfolio-db/. Overridable for tests / other
# machines via PORTFOLIODB_BACKUP_DIR.
DEFAULT_BACKUP_DIR = (
    Path.home() / "Library" / "CloudStorage" / "Dropbox"
    / "PJHub" / "portfolio-db" / "db_backups"
)
KEEP_DEFAULT = 30
_PREFIX = "portfolio-"
_PATTERN = "portfolio-*.db"


def backup_dir() -> Path:
    """Resolve the cold-backup directory (env override wins)."""
    override = os.environ.get("PORTFOLIODB_BACKUP_DIR")
    return Path(override).expanduser() if override else DEFAULT_BACKUP_DIR


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _verify_integrity(path: Path) -> None:
    """Run PRAGMA integrity_check on a snapshot; raise (and delete) if not ok."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    if not row or row[0] != "ok":
        path.unlink(missing_ok=True)
        raise RuntimeError(f"backup failed integrity_check ({path.name}): {row}")


def _rotate(dest_dir: Path, keep: int) -> list[Path]:
    """Keep the newest ``keep`` snapshots, delete older. Returns deleted paths.

    Also sweeps stale ``*.db.tmp`` left by a crashed run.
    """
    for junk in dest_dir.glob("*.db.tmp"):
        junk.unlink(missing_ok=True)
    if keep <= 0:
        return []
    snaps = sorted(dest_dir.glob(_PATTERN), key=lambda p: p.name, reverse=True)
    stale = snaps[keep:]
    for p in stale:
        p.unlink(missing_ok=True)
    return stale


def create_backup(keep: int = KEEP_DEFAULT) -> Path | None:
    """Create one consistent cold snapshot of portfolio.db.

    Returns the published snapshot Path, or ``None`` if there is no DB to back up
    (so a scheduled run on a not-yet-rebuilt machine is a clean no-op, not an
    error). Raises on integrity / write / verify failure.
    """
    if not DB_PATH.exists():
        return None

    dest_dir = backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    final = dest_dir / f"{_PREFIX}{_timestamp()}.db"
    tmp = final.with_name(final.name + ".tmp")

    # Online backup API: consistent snapshot, no WAL, safe while DB is in use.
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    if tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"backup produced an empty file: {tmp.name}")
    _verify_integrity(tmp)

    # Atomic publish within the same dir (Dropbox never sees a partial .db).
    tmp.replace(final)

    _rotate(dest_dir, keep)
    return final


def list_backups() -> list[Path]:
    """Newest-first list of available cold snapshots."""
    dest_dir = backup_dir()
    if not dest_dir.exists():
        return []
    return sorted(dest_dir.glob(_PATTERN), key=lambda p: p.name, reverse=True)


def restore_backup(src: Path, force: bool = False) -> Path:
    """Restore a snapshot into DB_PATH.

    Safety rails:
      - Snapshot is integrity-checked before it is trusted.
      - If a live DB already exists, refuse unless ``force`` — and even with
        ``force``, the current DB is copied to ``portfolio.pre-restore-*.db``
        first, so a restore is always reversible.
    """
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(src)
    _verify_integrity(src)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        if not force:
            raise FileExistsError(
                f"{DB_PATH} already exists; pass force=True to overwrite "
                "(the current DB will be saved to portfolio.pre-restore-*.db first)"
            )
        safety = DB_PATH.with_name(f"portfolio.pre-restore-{_timestamp()}.db")
        shutil.copy2(DB_PATH, safety)

    shutil.copy2(src, DB_PATH)
    return DB_PATH
