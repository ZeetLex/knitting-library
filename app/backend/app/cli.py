"""Administrative commands intended to be run inside the application container."""

from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt


DEFAULT_DB_PATH = Path("/data/recipes.db")
MIN_PASSWORD_LENGTH = 8


class PasswordResetError(Exception):
    """An expected error that can be shown safely to the operator."""


def reset_password(db_path: Path, username: str, new_password: str) -> None:
    """Reset a user's password and revoke all of their existing sessions."""
    username = username.strip()
    if not username:
        raise PasswordResetError("Username is required.")
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise PasswordResetError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if not db_path.is_file():
        raise PasswordResetError(f"Database not found at {db_path}.")

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None:
            raise PasswordResetError(f"User '{username}' was not found.")

        password_hash = bcrypt.hashpw(
            new_password.encode(), bcrypt.gensalt(rounds=12)
        ).decode()
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user["id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))

        # Current installations have this table. Keep recovery compatible with
        # older databases that predate the audit log.
        audit_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'user_action_log'"
        ).fetchone()
        if audit_table:
            conn.execute(
                """
                INSERT INTO user_action_log
                    (id, user_id, username, action, recipe_id, recipe_title,
                     metadata_json, created_at)
                VALUES (?, ?, ?, ?, NULL, '', ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user["id"],
                    user["username"],
                    "password_updated",
                    json.dumps({"method": "container_cli"}),
                    datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                ),
            )
        conn.commit()
    except PasswordResetError:
        if conn is not None:
            conn.rollback()
        raise
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise PasswordResetError(f"Could not update the database: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def _reset_password_command(username: str) -> None:
    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise PasswordResetError("Passwords do not match.")
    reset_password(DEFAULT_DB_PATH, username, password)
    print(f"Password reset for '{username}'. Existing sessions have been signed out.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    reset = subparsers.add_parser(
        "reset-password", help="interactively reset a user's password"
    )
    reset.add_argument("username", help="the exact username to update")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "reset-password":
            _reset_password_command(args.username)
    except (PasswordResetError, EOFError, KeyboardInterrupt) as exc:
        message = str(exc) or "Password reset cancelled."
        print(f"Error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
