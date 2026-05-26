"""DB migration scripts.

Each migration is a standalone module exposing `run(dry_run: bool) -> None`
and can be invoked via `python -m portfoliodb.migrations.<name>` with
`--dry-run` (default) or `--apply`. Migrations are idempotent: a second
run on already-canonical data should be a no-op.
"""
