"""Command-line entrypoint for the retail agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from retail_agent.config import Settings, load_settings
from retail_agent.db.bootstrap import bootstrap_database
from retail_agent.db.connection import get_connection


@dataclass(frozen=True)
class AppContext:
    """Application state shared across CLI turns."""

    settings: Settings
    conn: sqlite3.Connection


def main() -> int:
    """Start the application from the command line."""
    app_context = load_or_initialize_app()
    print_startup_banner(app_context.settings)
    return run_repl(app_context)


def load_or_initialize_app() -> AppContext:
    """Load configuration and prepare the initial application context."""
    settings = load_settings()
    conn = get_connection(settings.db_path)
    bootstrap_database(conn, settings.seed_data_dir)
    return AppContext(settings=settings, conn=conn)


def run_repl(app_context: AppContext) -> int:
    """Run the interactive terminal loop."""
    print("Type 'exit' or 'quit' to leave.")

    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 130

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            return 0

        try:
            response = handle_user_turn(user_input, app_context)
        except KeyboardInterrupt:
            print()
            return 130

        print(response)


def handle_user_turn(user_input: str, app_context: AppContext) -> str:
    """Handle a single user turn and return terminal output."""
    order_count = app_context.conn.execute("SELECT COUNT(*) AS count FROM orders").fetchone()[
        "count"
    ]
    return (
        f"Received input: {user_input}\n"
        f"Database is initialized and currently holds {order_count} seeded orders."
    )


def print_startup_banner(settings: Settings) -> None:
    """Render a concise startup banner with resolved paths."""
    print("Retail Store Agent")
    print(f"Database: {settings.db_path}")
    print(f"Seed data: {settings.seed_data_dir}")
    print(f"Model: {settings.model_name}")


def default_db_path(project_root: Path | None = None) -> Path:
    """Return the default SQLite path within the project workspace."""
    root = project_root or Path.cwd()
    return root / ".retail_agent" / "store.db"
