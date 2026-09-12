from __future__ import annotations

from typing import Protocol

from backend.simulation.domain.run import RunManifest, RunStatus, SimulationRunSpec


class SimulationRunRepository(Protocol):
    def create(self, run_id: str, spec: SimulationRunSpec, manifest: RunManifest) -> None: ...

    def get_status(self, run_id: str) -> RunStatus | None: ...

    def get_manifest(self, run_id: str) -> RunManifest | None: ...

    def get_request(self, run_id: str) -> dict | None: ...
