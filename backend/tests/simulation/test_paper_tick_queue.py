from __future__ import annotations

import asyncio

import pytest

from backend.paper_trading.service import PaperTradingEngine
from backend.simulation.adapters.live_tick_adapter import LiveTickAdapter


def test_tick_adapter_rejects_unknown_explicit_venue() -> None:
    with pytest.raises(ValueError, match="unknown explicit venue"):
        LiveTickAdapter().normalize({"symbol": "UNKNOWN:ABC", "ltp": 10})


def test_queue_overflow_is_observable_and_latest_tick_is_coalesced() -> None:
    engine = PaperTradingEngine()
    engine._started = True
    engine._queue = asyncio.Queue(maxsize=1)
    engine._on_tick({"symbol": "NSE:ABC", "ltp": 10})
    engine._on_tick({"symbol": "NSE:ABC", "ltp": 11})
    canonical = LiveTickAdapter().normalize({"symbol": "NSE:ABC", "ltp": 11})
    assert engine.queue_overflow_count == 1
    assert engine._coalesced_ticks[canonical.instrument.key]["ltp"] == 11
    assert engine._canonical_ticks[canonical.instrument.key].price == 11
