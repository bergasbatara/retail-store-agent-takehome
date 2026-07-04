"""Command-line entrypoint for the retail agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from retail_agent.config import Settings, load_settings


@dataclass(frozen=True)
class AppContext:
    """Application state shared across CLI turns."""

    settings: Settings


def main() -> int:
    """Start the application from the command line."""
    app_context = load_or_initialize_app()
    print_startup_banner(app_context.settings)
    return run_repl(app_context)


def load_or_initialize_app() -> AppContext:
    """Load configuration and prepare the initial application context."""
    settings = load_settings()
    return AppContext(settings=settings)


def run_repl(app_context: AppContext) -> int:
    """Run the interactive terminal loop."""
    print("Interactive agent runtime is not implemented yet.")
    return 0


def handle_user_turn(user_input: str, app_context: AppContext) -> str:
    """Handle a single user turn and return terminal output."""
    _ = app_context
    return f"Received input: {user_input}"


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
