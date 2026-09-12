from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any

from backend.simulation.domain.run import RunManifest, SimulationRunSpec
from backend.simulation.persistence.serializers import to_primitive

ENGINE_VERSION = "sim-daily-scaffold-v1a"


def canonical_json(value: Any) -> str:
    return json.dumps(to_primitive(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ManifestService:
    def __init__(self, *, engine_version: str = ENGINE_VERSION, git_commit: str | None = None):
        self.engine_version = engine_version
        self.git_commit = git_commit if git_commit is not None else os.getenv("GIT_COMMIT")

    def build(
        self,
        run_id: str,
        spec: SimulationRunSpec,
        *,
        dataset_hash: str | None = None,
        corporate_actions_hash: str | None = None,
        calendar_version: str | None = None,
        created_at: datetime | None = None,
    ) -> RunManifest:
        strategy_context_hash = sha256_value(spec.strategy_context)
        strategy_hash = sha256_value({"key": spec.strategy, "context": spec.strategy_context})
        universe_hash = sha256_value([instrument.key for instrument in spec.universe])
        execution_hash = sha256_value(spec.execution_profile)
        commission_hash = sha256_value(spec.commission_profile)
        settlement_hash = sha256_value(spec.settlement_profile)
        request_hash = sha256_value(spec)
        deterministic = {
            "engine_version": self.engine_version,
            "git_commit": self.git_commit,
            "strategy_hash": strategy_hash,
            "strategy_key": spec.strategy,
            "strategy_context_hash": strategy_context_hash,
            "data_version_id": spec.data_version_id,
            "dataset_hash": dataset_hash,
            "universe_hash": universe_hash,
            "corporate_actions_hash": corporate_actions_hash,
            "calendar_version": calendar_version,
            "execution_profile_hash": execution_hash,
            "commission_profile_hash": commission_hash,
            "settlement_profile_hash": settlement_hash,
            "seed": spec.seed,
            "request_hash": request_hash,
        }
        return RunManifest(
            run_id=run_id,
            **deterministic,
            manifest_hash=sha256_value(deterministic),
            created_at=created_at or datetime.now(timezone.utc),
        )
