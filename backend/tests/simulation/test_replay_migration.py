from __future__ import annotations

from pathlib import Path
import os
import shutil
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(path: Path) -> Config:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path.resolve().as_posix()}")
    return config


def test_replay_migration_fresh_upgrade_downgrade_and_retention() -> None:
    directory = Path(".pytest_phase2c") / uuid4().hex
    directory.mkdir(parents=True)
    database = directory / "migration.db"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.resolve().as_posix()}"
    try:
        config = _config(database)
        command.upgrade(config, "0015_backtest_paper_reconciliation")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO data_versions (id,name,description,source,is_active,created_at,metadata_json) VALUES ('v','v','','internal',1,CURRENT_TIMESTAMP,'{}')"))
            connection.execute(text("INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) VALUES ('sim_keep','BACKTEST','VERIFIED','DONE','s','h','e',1,'{}','{}','',CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) VALUES ('sim_paper','PAPER','RESEARCH','RUNNING','s','h','e',1,'{}','{}','',CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO simulation_reconciliations (id,baseline_run_id,paper_run_id,status,alignment_policy,allow_research_baseline,include_low_confidence,paper_cutoff_sequence,paper_cutoff_time,request_hash,compatibility_json,summary_json,calibration_json,report_json,error,created_at) VALUES ('rec_keep','sim_keep','sim_paper','DONE','KEYED_THEN_SIGNATURE',0,1,1,CURRENT_TIMESTAMP,'request_keep','{}','{}','{}','{}','',CURRENT_TIMESTAMP)"))
        engine.dispose()
        command.upgrade(config, "head")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        assert "simulation_replay_sessions" in inspect(engine).get_table_names()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO simulation_runs (id,mode,verification_level,status,strategy_key,strategy_hash,engine_version,seed,request_json,manifest_json,error,created_at) VALUES ('sim_replay','REPLAY','VERIFIED','RUNNING','s','h','e',1,'{}','{}','',CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO simulation_replay_sessions (run_id,control_status,start_session,end_session,completed_sessions,total_sessions,last_event_sequence,strategy_state_json,initialized,finish_called,created_at,updated_at) VALUES ('sim_replay','READY','2024-01-01','2024-01-02',0,2,0,'{}',0,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        engine.dispose()
        command.downgrade(config, "0015_backtest_paper_reconciliation")
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        assert "simulation_replay_sessions" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_keep'")).scalar_one() == "sim_keep"
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_paper'")).scalar_one() == "sim_paper"
            assert connection.execute(text("SELECT id FROM simulation_runs WHERE id='sim_replay'")).scalar_one() == "sim_replay"
            assert connection.execute(text("SELECT id FROM simulation_reconciliations WHERE id='rec_keep'")).scalar_one() == "rec_keep"
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        shutil.rmtree(directory, ignore_errors=True)
