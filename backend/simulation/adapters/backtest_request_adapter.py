from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.simulation.domain.enums import SimulationMode, VerificationLevel
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.run import SimulationRunSpec


VENUE_CURRENCIES = {
    "NSE": "INR",
    "BSE": "INR",
    "NASDAQ": "USD",
    "NYSE": "USD",
    "AMEX": "USD",
}


def should_use_simulation_engine(request: Any) -> bool:
    return str(getattr(request, "verification_level", "RESEARCH")).strip().upper() == "VERIFIED"


class BacktestRequestAdapter:
    """Translate an explicit VERIFIED legacy request into a canonical run spec."""

    def to_spec(self, request: Any) -> SimulationRunSpec:
        if not should_use_simulation_engine(request):
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: request is not VERIFIED")
        if str(request.timeframe).strip().lower() != "1d":
            raise ValueError("UNSUPPORTED_VERIFIED_TIMEFRAME: VERIFIED requires timeframe=1d")
        if not request.data_version_id:
            raise ValueError("DATA_VERSION_REQUIRED: VERIFIED requires data_version_id")
        if not request.start:
            raise ValueError("VERIFIED_START_REQUIRED: VERIFIED requires start")
        if not request.end:
            raise ValueError("VERIFIED_END_REQUIRED: VERIFIED requires end")

        venue = str(request.market).strip().upper()
        if venue not in VENUE_CURRENCIES:
            raise ValueError(f"UNSUPPORTED_VERIFIED_VENUE: {venue}")
        currency = str(request.currency or VENUE_CURRENCIES[venue]).strip().upper()
        if currency != VENUE_CURRENCIES[venue]:
            raise ValueError(f"UNSUPPORTED_VERIFIED_CONFIG: {venue} requires {VENUE_CURRENCIES[venue]}")

        try:
            start = date.fromisoformat(str(request.start))
            end = date.fromisoformat(str(request.end))
        except ValueError as exc:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: dates must use YYYY-MM-DD") from exc
        if end < start:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: end precedes start")

        config = dict(request.config or {})
        if config.get("position_fraction") is not None:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: position_fraction is not supported")
        if config.get("allow_short") is True:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: shorting is not supported")
        if int(config.get("fill_delay_bars", 0)) != 0:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: fill_delay_bars is not supported")
        if bool(config.get("intraday_slippage_model", False)):
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: intraday slippage is not supported")
        if str(config.get("timeframe", "1d")).lower() != "1d":
            raise ValueError("UNSUPPORTED_VERIFIED_TIMEFRAME: config timeframe must be 1d")

        context = dict(request.context or {})
        quantity = context.get("quantity", config.get("position_size", 1))
        try:
            quantity = Decimal(str(quantity))
        except Exception as exc:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: quantity must be decimal-compatible") from exc
        if quantity <= 0:
            raise ValueError("UNSUPPORTED_VERIFIED_CONFIG: quantity must be positive")
        context["quantity"] = str(quantity)

        symbol = str(request.asset or request.symbol).strip().upper()
        instrument = InstrumentId(symbol, venue, "EQUITY", currency)
        return SimulationRunSpec(
            mode=SimulationMode.BACKTEST,
            verification_level=VerificationLevel.VERIFIED,
            strategy=str(request.strategy),
            strategy_context=context,
            universe=(instrument,),
            start=start,
            end=end,
            initial_cash=Decimal(str(config.get("initial_cash", 100000))),
            base_currency=currency,
            data_version_id=str(request.data_version_id),
            execution_profile={
                "model": "fixed_bps",
                "slippage_bps": str(config.get("slippage_bps", 0)),
                "max_participation": "1",
                "daily_bar_path_policy": "WORST_CASE",
            },
            commission_profile={
                "model": "bps",
                "bps": str(config.get("fee_bps", 0)),
                "minimum": "0",
            },
            settlement_profile={"settlement_days": 1},
            seed=42,
        )
