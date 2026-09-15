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


def test_phase3c_migration_upgrade_downgrade_and_retention() -> None:
    directory = Path(".pytest_phase3c") / uuid4().hex
    directory.mkdir(parents=True)
    database = directory / "migration.db"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.resolve().as_posix()}"
    try:
        config = _config(database)
        command.upgrade(config, "0018_strategy_governance")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,email,hashed_password,role,created_at) VALUES ('u','u@example.com','x','ADMIN',CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) VALUES ('sim_base','BACKTEST','VERIFIED','DONE','s','h','e',1,'{}','{}','',CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) VALUES ('sim_paper','PAPER','RESEARCH','RUNNING','s','h','e',1,'{}','{}','',CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO virtual_portfolios (id,user_id,name,initial_capital,current_cash,created_at,is_active,simulation_run_id) VALUES ('vp','u','legacy paper',100,100,CURRENT_TIMESTAMP,1,'sim_paper')"))
            connection.execute(text("INSERT INTO strategy_governance_records (id,strategy_key,strategy_hash,current_stage,baseline_run_id,latest_evidence_hash,policy_version,created_at,updated_at) VALUES ('gov','s','h','STAGING','sim_base','eh','v1',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO strategy_governance_decisions (id,governance_record_id,decision_type,from_stage,to_stage,baseline_run_id,policy_version,policy_snapshot_json,evidence_hash,evidence_json,checks_json,reason,actor_user_id,request_hash,created_at) VALUES ('gdec','gov','PROMOTE','CANDIDATE','STAGING','sim_base','v1','{}','eh','{}','[]','ok','u','rh',CURRENT_TIMESTAMP)"))
        engine.dispose()
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        assert {"paper_strategy_deployments", "paper_strategy_inputs", "paper_strategy_intents", "paper_strategy_events"} <= set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM virtual_portfolios WHERE id='vp'")).scalar_one() == "vp"
            assert connection.execute(text("SELECT id FROM strategy_governance_records WHERE id='gov'")).scalar_one() == "gov"
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_paper'")).scalar_one() == "sim_paper"
        engine.dispose()
        command.downgrade(config, "0018_strategy_governance")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        assert not ({"paper_strategy_deployments", "paper_strategy_inputs", "paper_strategy_intents", "paper_strategy_events"} & set(inspect(engine).get_table_names()))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM virtual_portfolios WHERE id='vp'")).scalar_one() == "vp"
            assert connection.execute(text("SELECT id FROM strategy_governance_records WHERE id='gov'")).scalar_one() == "gov"
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        shutil.rmtree(directory, ignore_errors=True)
