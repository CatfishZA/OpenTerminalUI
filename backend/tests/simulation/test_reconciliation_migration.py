from __future__ import annotations

from pathlib import Path
import os
import shutil
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(path) -> Config:  # noqa: ANN001
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path.resolve().as_posix()}")
    return config


def _workspace_temp() -> tuple[Path, Path]:
    directory = Path(".pytest_phase2b") / uuid4().hex
    directory.mkdir(parents=True)
    return directory, directory / "migration.db"


def _set_database(database: Path) -> str | None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.resolve().as_posix()}"
    return previous


def _restore_database(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous


def test_fresh_migration_chain_and_downgrade() -> None:
    directory, database = _workspace_temp()
    previous = _set_database(database)
    try:
        config = _config(database)
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        assert {"simulation_reconciliations", "simulation_reconciliation_items", "simulation_execution_observations"} <= set(inspect(engine).get_table_names())
        engine.dispose()
        command.downgrade(config, "0014_paper_simulation_link")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        assert not ({"simulation_reconciliations", "simulation_reconciliation_items", "simulation_execution_observations"} & set(inspect(engine).get_table_names()))
        engine.dispose()
    finally:
        _restore_database(previous)
        shutil.rmtree(directory, ignore_errors=True)


def test_phase2a_upgrade_retains_source_rows() -> None:
    directory, database = _workspace_temp()
    previous = _set_database(database)
    try:
        config = _config(database)
        command.upgrade(config, "0014_paper_simulation_link")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, email, hashed_password, role, created_at) VALUES ('u', 'u@example.com', 'x', 'VIEWER', CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO virtual_portfolios (id, user_id, name, initial_capital, current_cash, created_at, is_active, simulation_run_id) VALUES ('p', 'u', 'legacy', 1000, 1000, CURRENT_TIMESTAMP, 1, NULL)"))
        engine.dispose()
        command.upgrade(config, "head")
        command.downgrade(config, "0014_paper_simulation_link")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT name, current_cash FROM virtual_portfolios WHERE id='p'" )).one() == ("legacy", 1000.0)
        engine.dispose()
    finally:
        _restore_database(previous)
        shutil.rmtree(directory, ignore_errors=True)
