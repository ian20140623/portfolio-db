"""User management: create and list users."""

from portfoliodb.db import get_connection
from portfoliodb.models import User


def create_user(username: str, display_name: str) -> User:
    """Create a new user. Raises if username already exists."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, display_name) VALUES (?, ?)",
            (username, display_name),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return User.from_row(row)


def get_user(user_id: int) -> User:
    """Get a user by ID. Raises if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"User ID {user_id} not found")
        return User.from_row(row)


def get_user_by_username(username: str) -> User:
    """Get a user by username. Raises if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ValueError(f"User '{username}' not found")
        return User.from_row(row)


def list_users() -> list[User]:
    """List all users."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY id"
        ).fetchall()
        return [User.from_row(r) for r in rows]
