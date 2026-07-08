"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_parent_dir(db_path: Path) -> None:
    """Ensure the parent directory for the SQLite file exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for the application."""
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
