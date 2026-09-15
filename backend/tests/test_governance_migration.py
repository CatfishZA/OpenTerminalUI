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


def test_governance_migration_fresh_upgrade_downgrade_and_retention() -> None:
    directory = Path(".pytest_phase3b") / uuid4().hex
    directory.mkdir(parents=True)
    database = directory / "migration.db"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.resolve().as_posix()}"
    try:
        config = _config(database)
        command.upgrade(config, "0017_corporate_actions_data_integrity")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO model_registry (id,name,run_id,stage,promoted_at,metadata_json,created_at) "
                "VALUES ('legacy-reg','legacy',NULL,'prod',CURRENT_TIMESTAMP,'{}',CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) "
                "VALUES ('sim_keep','BACKTEST','VERIFIED','DONE','fixture:sma','hash-a','engine',1,'{}','{}','',CURRENT_TIMESTAMP)"
            ))
        engine.dispose()
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        inspector = inspect(engine)
        assert {"strategy_governance_records", "strategy_governance_decisions"} <= set(inspector.get_table_names())
        assert {"simulation_run_id", "governance_record_id", "governance_decision_id", "evidence_hash", "evidence_level"} <= {
            column["name"] for column in inspector.get_columns("model_registry")
        }
        with engine.connect() as connection:
            assert connection.execute(text("SELECT name FROM model_registry WHERE id='legacy-reg'")).scalar_one() == "legacy"
            assert connection.execute(text("SELECT evidence_level FROM model_registry WHERE id='legacy-reg'")).scalar_one() == "LEGACY"
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_keep'")).scalar_one() == "sim_keep"
        engine.dispose()
        command.downgrade(config, "0017_corporate_actions_data_integrity")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        inspector = inspect(engine)
        assert "strategy_governance_records" not in inspector.get_table_names()
        assert "simulation_run_id" not in {column["name"] for column in inspector.get_columns("model_registry")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT name FROM model_registry WHERE id='legacy-reg'")).scalar_one() == "legacy"
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_keep'")).scalar_one() == "sim_keep"
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        shutil.rmtree(directory, ignore_errors=True)
