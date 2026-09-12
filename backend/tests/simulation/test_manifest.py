from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from backend.simulation.services.manifest_service import ManifestService
from backend.tests.simulation.fixtures import run_spec


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _hash(spec) -> str:  # noqa: ANN001
    return ManifestService(engine_version="test-v1", git_commit="abc123").build(
        "sim_test", spec, created_at=NOW
    ).manifest_hash


def test_same_configuration_produces_same_manifest_hash() -> None:
    assert _hash(run_spec()) == _hash(run_spec())


def test_strategy_parameter_change_changes_manifest_hash() -> None:
    spec = run_spec()
    assert _hash(spec) != _hash(replace(spec, strategy_context={"short_window": 10, "long_window": 50}))


def test_execution_model_change_changes_manifest_hash() -> None:
    spec = run_spec()
    assert _hash(spec) != _hash(replace(spec, execution_profile={"model": "volume_participation"}))


def test_seed_change_changes_manifest_hash() -> None:
    spec = run_spec()
    assert _hash(spec) != _hash(replace(spec, seed=43))


def test_run_id_and_creation_time_are_not_deterministic_hash_inputs() -> None:
    service = ManifestService(engine_version="test-v1", git_commit="abc123")
    first = service.build("sim_one", run_spec(), created_at=NOW)
    second = service.build("sim_two", run_spec(), created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert first.manifest_hash == second.manifest_hash
