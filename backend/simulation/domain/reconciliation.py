from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReconciliationStatus(str, Enum):
    BUILDING = "BUILDING"
    DONE = "DONE"
    FAILED = "FAILED"


class AlignmentPolicy(str, Enum):
    KEYED_THEN_SIGNATURE = "KEYED_THEN_SIGNATURE"
    KEYS_ONLY = "KEYS_ONLY"


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    BASELINE_ONLY = "BASELINE_ONLY"
    PAPER_ONLY = "PAPER_ONLY"
    AMBIGUOUS = "AMBIGUOUS"


class MatchBasis(str, Enum):
    RECONCILIATION_KEY = "RECONCILIATION_KEY"
    STRATEGY_ORDER_ID = "STRATEGY_ORDER_ID"
    UNIQUE_SIGNATURE = "UNIQUE_SIGNATURE"
    ORDINAL_FALLBACK = "ORDINAL_FALLBACK"
    NONE = "NONE"


class MatchConfidence(str, Enum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class BacktestPaperReconciliationSpec:
    baseline_run_id: str
    paper_run_id: str
    alignment_policy: AlignmentPolicy = AlignmentPolicy.KEYED_THEN_SIGNATURE
    paper_cutoff_sequence: int | None = None
    allow_research_baseline: bool = False
    include_low_confidence_matches: bool = True

    def __post_init__(self) -> None:
        if not self.baseline_run_id or not self.paper_run_id:
            raise ValueError("source run ids are required")
        if self.paper_cutoff_sequence is not None and self.paper_cutoff_sequence < 1:
            raise ValueError("paper cutoff sequence must be positive")
