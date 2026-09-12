from __future__ import annotations

from dataclasses import dataclass
import re

_PART = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")


def _canonical_part(value: str, label: str) -> str:
    canonical = str(value).strip().upper()
    if not canonical or not _PART.fullmatch(canonical):
        raise ValueError(f"{label} must be a non-empty canonical identifier")
    return canonical


@dataclass(frozen=True, slots=True)
class InstrumentId:
    symbol: str
    venue: str
    asset_class: str
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _canonical_part(self.symbol, "symbol"))
        object.__setattr__(self, "venue", _canonical_part(self.venue, "venue"))
        object.__setattr__(self, "asset_class", _canonical_part(self.asset_class, "asset_class"))
        currency = _canonical_part(self.currency, "currency")
        if len(currency) != 3:
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)

    @property
    def key(self) -> str:
        return f"{self.venue}:{self.asset_class}:{self.symbol}:{self.currency}"

    @classmethod
    def parse(cls, value: str) -> "InstrumentId":
        parts = value.split(":")
        if len(parts) != 4:
            raise ValueError("instrument key must be VENUE:ASSET_CLASS:SYMBOL:CURRENCY")
        return cls(symbol=parts[2], venue=parts[0], asset_class=parts[1], currency=parts[3])

    def __str__(self) -> str:
        return self.key


@dataclass(frozen=True, slots=True)
class AccountId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("account id is required")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RunId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.startswith("sim_"):
            raise ValueError("simulation run id must start with 'sim_'")

    def __str__(self) -> str:
        return self.value
