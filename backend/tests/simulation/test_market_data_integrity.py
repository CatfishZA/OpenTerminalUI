from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from backend.models import PriceEodORM
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import MarketBar, MarketDataManifest
from backend.simulation.persistence.models import SimulationRunORM
from backend.simulation.services.market_data_integrity_service import MarketDataIntegrityService
from backend.simulation.services.replay_simulation_service import ReplaySimulationError, ReplaySimulationService
from backend.tests.simulation.fixtures import instrument
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def _bar(inst: InstrumentId, day: int, *, version: str = "v1", price: str = "100", volume: str = "10") -> MarketBar:
    value = Decimal(price)
    session = date(2024, 1, day)
    return MarketBar(
        inst,
        datetime.combine(session, time(14, 30), timezone.utc),
        datetime.combine(session, time(21), timezone.utc),
        value, value + 1, value - 1, value, Decimal(volume), version,
    )


def _manifest(*instruments: InstrumentId) -> MarketDataManifest:
    return MarketDataManifest(
        "v1", "hash", instruments, date(2024, 1, 1), date(2024, 1, 3),
        "persisted", False, "fixture-v1",
    )


def test_integrity_rejects_missing_wrong_version_duplicate_and_non_monotonic_bars() -> None:
    service = MarketDataIntegrityService()
    first = instrument()
    second = InstrumentId("MSFT", "NASDAQ", "EQUITY", "USD")
    spec = replace(replay_spec(), universe=(first, second), start=date(2024, 1, 1), end=date(2024, 1, 3), data_version_id="v1")
    bars = [_bar(first, 2), _bar(first, 1), _bar(first, 1), _bar(second, 1), _bar(second, 2, version="wrong")]
    report = service.validate(spec, bars, manifest=_manifest(first, second))
    codes = {item.code for item in report.errors}
    assert {"DUPLICATE_BAR", "VERIFIED_DATA_MISSING"} <= codes
    assert any("wrong data version" in item.message for item in report.errors)
    assert any("not monotonic" in item.message for item in report.errors)
    with pytest.raises(ValueError, match="DUPLICATE_BAR|VERIFIED_DATA_MISSING"):
        service.require_valid(report)


def test_integrity_allows_zero_volume_warns_without_mutating_and_hashes_deterministically() -> None:
    service = MarketDataIntegrityService()
    inst = instrument()
    spec = replace(replay_spec(), start=date(2024, 1, 1), end=date(2024, 1, 2), data_version_id="v1")
    bars = [_bar(inst, 1, volume="0"), _bar(inst, 2, price="1000")]
    before = tuple(bars)
    first = service.validate(spec, bars, manifest=_manifest(inst))
    second = service.validate(spec, list(bars), manifest=_manifest(inst))
    assert not first.errors
    assert "SUSPICIOUS_PRICE_DISCONTINUITY" in {item.code for item in first.warnings}
    assert first.report_hash == second.report_hash
    assert tuple(bars) == before


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((0, 1, 1, 1, 0), "positive"),
        ((10, 9, 8, 10, 0), "range"),
        ((10, 11, 10.5, 10, 0), "range"),
        ((10, 11, 9, 10, -1), "negative"),
    ],
)
def test_raw_bar_validation_rejects_invalid_ohlc_and_negative_volume(values, message) -> None:  # noqa: ANN001
    with pytest.raises(ValueError, match=message):
        MarketDataIntegrityService.validate_bar_values(
            open_price=values[0], high=values[1], low=values[2], close=values[3], volume=values[4],
            instrument="AAPL", session="2024-01-01",
        )


def test_verified_invalid_source_fails_before_run_and_does_not_mutate_source(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    row = db_session.query(PriceEodORM).filter_by(data_version_id="replay-v1", trade_date="2024-01-03").one()
    row.volume = -1
    db_session.commit()
    with pytest.raises(ReplaySimulationError) as raised:
        asyncio.run(ReplaySimulationService(db_session).create(replay_spec()))
    assert raised.value.code == "INVALID_OHLC"
    assert db_session.query(SimulationRunORM).count() == 0
    assert db_session.query(PriceEodORM).filter_by(data_version_id="replay-v1", trade_date="2024-01-03").one().volume == -1
