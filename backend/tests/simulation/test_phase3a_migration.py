from __future__ import annotations

import os
from pathlib import Path
import shutil
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(path: Path) -> Config:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path.resolve().as_posix()}")
    return config


def test_phase3a_migration_fresh_upgrade_and_legacy_row_retention() -> None:
    directory = Path(".pytest_phase3a") / uuid4().hex
    directory.mkdir(parents=True)
    database = directory / "migration.db"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.resolve().as_posix()}"
    try:
        config = _config(database)
        command.upgrade(config, "0016_historical_replay")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO corp_actions (id,symbol,action_date,action_type,factor,amount,notes,data_version_id,created_at) "
                "VALUES ('legacy-ca','AAPL','2024-01-03','DIVIDEND',1,2,'legacy',NULL,CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) "
                "VALUES ('sim_keep','REPLAY','VERIFIED','DONE','s','h','e',1,'{}','{}','',CURRENT_TIMESTAMP)"
            ))
        engine.dispose()
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        inspector = inspect(engine)
        assert "simulation_corporate_action_entitlements" in inspector.get_table_names()
        columns = {item["name"] for item in inspector.get_columns("corp_actions")}
        assert {"ex_date", "record_date", "pay_date", "currency", "source", "metadata_json"} <= columns
        with engine.connect() as connection:
            row = connection.execute(text("SELECT id, notes, ex_date FROM corp_actions WHERE id='legacy-ca'")).one()
            assert tuple(row) == ("legacy-ca", "legacy", None)
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_keep'")).scalar_one() == "sim_keep"
        engine.dispose()
        command.downgrade(config, "0016_historical_replay")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        inspector = inspect(engine)
        assert "simulation_corporate_action_entitlements" not in inspector.get_table_names()
        assert "ex_date" not in {item["name"] for item in inspector.get_columns("corp_actions")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM corp_actions WHERE id='legacy-ca'")).scalar_one() == "legacy-ca"
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_keep'")).scalar_one() == "sim_keep"
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        shutil.rmtree(directory, ignore_errors=True)
