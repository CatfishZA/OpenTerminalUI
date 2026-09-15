from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GovernanceStage(str, Enum):
    CANDIDATE = "CANDIDATE"
    STAGING = "STAGING"
    PROD = "PROD"
    REVOKED = "REVOKED"


class GovernanceDecisionType(str, Enum):
    PROMOTE = "PROMOTE"
    REVOKE = "REVOKE"


@dataclass(frozen=True, slots=True)
class GovernanceCheck:
    code: str
    passed: bool
    blocking: bool
    detail: str
    failure_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "passed": self.passed,
            "blocking": self.blocking,
            "detail": self.detail,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True, slots=True)
class GovernanceEvaluation:
    target_stage: GovernanceStage
    current_stage: GovernanceStage
    eligible: bool
    checks: tuple[GovernanceCheck, ...]
    evidence: dict[str, Any]
    evidence_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_stage": self.target_stage.value,
            "current_stage": self.current_stage.value,
            "eligible": self.eligible,
            "checks": [check.as_dict() for check in self.checks],
            "evidence": self.evidence,
            "evidence_hash": self.evidence_hash,
        }
