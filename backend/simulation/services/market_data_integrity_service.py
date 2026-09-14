from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import CorporateActionType, VerificationLevel
from backend.simulation.domain.market import MarketBar, MarketDataManifest
from backend.simulation.domain.run import SimulationRunSpec
from backend.simulation.services.manifest_service import sha256_value


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    code: str
    message: str
    instrument: str | None = None
    session: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "instrument": self.instrument,
            "session": self.session,
        }


@dataclass(frozen=True, slots=True)
class MarketDataIntegrityReport:
    status: str
    data_version_id: str | None
    bar_count: int
    instruments: dict[str, dict[str, Any]]
    errors: tuple[DataQualityIssue, ...]
    warnings: tuple[DataQualityIssue, ...]
    corporate_actions: dict[str, int]
    legacy_assumptions: tuple[str, ...]
    report_hash: str

    def as_dict(self, *, applied: int = 0) -> dict[str, Any]:
        return {
            "status": self.status,
            "data_version_id": self.data_version_id,
            "bar_count": self.bar_count,
            "instruments": self.instruments,
            "errors": [item.as_dict() for item in self.errors],
            "warnings": [item.as_dict() for item in self.warnings],
            "corporate_actions": {**self.corporate_actions, "applied": applied},
            "legacy_assumptions": list(self.legacy_assumptions),
            "integrity_report_hash": self.report_hash,
        }


class MarketDataIntegrityService:
    """Canonical, non-mutating preflight for historical BACKTEST and REPLAY."""

    @staticmethod
    def validate_bar_values(*, open_price, high, low, close, volume, instrument: str, session: str) -> None:  # noqa: ANN001
        prices = tuple(Decimal(str(value)) for value in (open_price, high, low, close))
        if any(price <= 0 for price in prices):
            raise ValueError(f"INVALID_OHLC: OHLC prices must be positive instrument={instrument} session={session}")
        open_value, high_value, low_value, close_value = prices
        if high_value < max(open_value, low_value, close_value) or low_value > min(open_value, high_value, close_value):
            raise ValueError(f"INVALID_OHLC: invalid OHLC range instrument={instrument} session={session}")
        if Decimal(str(volume)) < 0:
            raise ValueError(f"INVALID_OHLC: volume must not be negative instrument={instrument} session={session}")

    def validate(
        self,
        spec: SimulationRunSpec,
        bars: Iterable[MarketBar],
        *,
        actions: Iterable[CorporateAction] = (),
        manifest: MarketDataManifest | None = None,
    ) -> MarketDataIntegrityReport:
        values = list(bars)
        action_values = list(actions)
        errors: list[DataQualityIssue] = []
        warnings: list[DataQualityIssue] = []
        grouped = {instrument: [] for instrument in spec.universe}

        for bar in values:
            key = bar.instrument.key
            if bar.instrument not in grouped:
                errors.append(DataQualityIssue("INSTRUMENT_DATA_NOT_FOUND", "bar is outside requested universe", key, bar.ts_open.date().isoformat()))
                continue
            grouped[bar.instrument].append(bar)
            session = bar.ts_open.date().isoformat()
            if bar.ts_open.date() < spec.start or bar.ts_open.date() > spec.end:
                errors.append(DataQualityIssue("VERIFIED_DATA_MISSING", "bar is outside requested date range", key, session))
            if spec.data_version_id and bar.data_version_id != spec.data_version_id:
                errors.append(DataQualityIssue("VERIFIED_DATA_MISSING", f"wrong data version; expected {spec.data_version_id}", key, session))
            prices = (bar.open, bar.high, bar.low, bar.close)
            if any(price <= 0 for price in prices):
                errors.append(DataQualityIssue("INVALID_OHLC", "OHLC prices must be positive", key, session))
            if not (bar.high >= bar.open and bar.high >= bar.close and bar.high >= bar.low):
                errors.append(DataQualityIssue("INVALID_OHLC", "high is below open, close, or low", key, session))
            if not (bar.low <= bar.open and bar.low <= bar.close and bar.low <= bar.high):
                errors.append(DataQualityIssue("INVALID_OHLC", "low is above open, close, or high", key, session))
            if bar.volume < 0:
                errors.append(DataQualityIssue("INVALID_OHLC", "volume must not be negative", key, session))

        expected_sessions = sorted({bar.ts_open.date() for bar in values})
        summaries: dict[str, dict[str, Any]] = {}
        split_dates = {(action.instrument, action.ex_date) for action in action_values if action.action_type is CorporateActionType.SPLIT}
        for instrument, instrument_bars in grouped.items():
            key = instrument.key
            sessions = [bar.ts_open.date() for bar in instrument_bars]
            if not instrument_bars:
                errors.append(DataQualityIssue("INSTRUMENT_DATA_NOT_FOUND", "no persisted bars", key))
            if sessions != sorted(sessions):
                errors.append(DataQualityIssue("VERIFIED_DATA_MISSING", "sessions are not monotonic", key))
            duplicates = sorted({session for session in sessions if sessions.count(session) > 1})
            for session in duplicates:
                errors.append(DataQualityIssue("DUPLICATE_BAR", "duplicate daily bar", key, session.isoformat()))
            missing = sorted(set(expected_sessions) - set(sessions)) if spec.verification_level is VerificationLevel.VERIFIED else []
            for session in missing:
                errors.append(DataQualityIssue("VERIFIED_DATA_MISSING", f"missing session for data version {spec.data_version_id}", key, session.isoformat()))
            ordered = sorted(instrument_bars, key=lambda bar: bar.ts_open)
            for previous, current in zip(ordered, ordered[1:]):
                ratio = current.open / previous.close
                if (ratio >= Decimal("5") or ratio <= Decimal("0.2")) and (instrument, current.ts_open.date()) not in split_dates:
                    warnings.append(DataQualityIssue("SUSPICIOUS_PRICE_DISCONTINUITY", "extreme overnight price ratio without matching split", key, current.ts_open.date().isoformat()))
            summaries[key] = {
                "bars": len(instrument_bars),
                "first_session": min(sessions).isoformat() if sessions else None,
                "last_session": max(sessions).isoformat() if sessions else None,
                "missing_sessions": [session.isoformat() for session in missing],
            }

        for action in action_values:
            warnings.extend(DataQualityIssue(code, "legacy corporate-action compatibility assumption", action.instrument.key, action.ex_date.isoformat()) for code in action.warnings)
            if action.action_type is CorporateActionType.SPLIT:
                ordered = sorted(grouped.get(action.instrument, []), key=lambda bar: bar.ts_open)
                previous = next((bar for bar in reversed(ordered) if bar.ts_open.date() < action.ex_date), None)
                current = next((bar for bar in ordered if bar.ts_open.date() == action.ex_date), None)
                if previous and current and action.factor:
                    expected_open = previous.close / action.factor
                    ratio = current.open / expected_open if expected_open else Decimal(1)
                    if ratio >= Decimal("2") or ratio <= Decimal("0.5"):
                        warnings.append(DataQualityIssue("SPLIT_PRICE_DISCONTINUITY_UNEXPLAINED", "split and unadjusted price movement are inconsistent", action.instrument.key, action.ex_date.isoformat()))

        if manifest and manifest.adjusted and action_values:
            errors.append(DataQualityIssue("ADJUSTED_DATA_CORPORATE_ACTION_CONFLICT", "adjusted prices cannot also apply account-level corporate actions"))
        if not manifest or not manifest.calendar_version:
            warnings.append(DataQualityIssue("AUTHORITATIVE_CALENDAR_UNAVAILABLE", "coverage is internally validated without an authoritative exchange calendar"))

        errors = self._dedupe(errors)
        warnings = self._dedupe(warnings)
        action_summary = {
            "found": len(action_values),
            "splits": sum(action.action_type is CorporateActionType.SPLIT for action in action_values),
            "cash_dividends": sum(action.action_type is CorporateActionType.CASH_DIVIDEND for action in action_values),
        }
        legacy = tuple(sorted({issue.code for issue in warnings if issue.code.startswith("LEGACY_")}))
        basis = {
            "status": "INVALID" if errors else "VALID",
            "data_version_id": spec.data_version_id,
            "bar_count": len(values),
            "instruments": summaries,
            "errors": [item.as_dict() for item in errors],
            "warnings": [item.as_dict() for item in warnings],
            "corporate_actions": action_summary,
            "legacy_assumptions": legacy,
        }
        return MarketDataIntegrityReport(
            basis["status"], spec.data_version_id, len(values), summaries,
            tuple(errors), tuple(warnings), action_summary, legacy, sha256_value(basis),
        )

    @staticmethod
    def require_valid(report: MarketDataIntegrityReport) -> None:
        if report.errors:
            first = report.errors[0]
            detail = f" instrument={first.instrument}" if first.instrument else ""
            detail += f" session={first.session}" if first.session else ""
            raise ValueError(f"{first.code}: {first.message}{detail}")

    @staticmethod
    def _dedupe(values: list[DataQualityIssue]) -> list[DataQualityIssue]:
        unique = {(item.code, item.message, item.instrument, item.session): item for item in values}
        return [unique[key] for key in sorted(unique, key=lambda item: tuple("" if part is None else part for part in item))]
