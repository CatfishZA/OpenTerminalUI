from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class CanonicalGovernancePolicy:
    version: str = "canonical-governance-v1"
    staging_requires_verified: bool = True
    staging_requires_valid_data: bool = True
    staging_requires_accounting_reconciliation: bool = True
    staging_allow_missing_code_hash: bool = True
    staging_allow_empty_strategy: bool = False
    prod_requires_staging: bool = True
    prod_requires_code_hash: bool = True
    prod_requires_paper: bool = True
    prod_requires_reconciliation: bool = True
    prod_requires_exact_strategy_identity: bool = True
    prod_max_ambiguous_matches: int = 0
    prod_max_low_confidence_matches: int = 0
    prod_max_baseline_only: int = 0
    prod_max_paper_only: int = 0
    prod_min_matched_orders: int = 1
    prod_min_paper_fills: int = 1

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_GOVERNANCE_POLICY = CanonicalGovernancePolicy()
