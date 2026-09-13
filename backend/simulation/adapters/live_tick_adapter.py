from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.ticks import MarketTick


VENUE_CURRENCIES = {
    "NSE": "INR",
    "BSE": "INR",
    "NASDAQ": "USD",
    "NYSE": "USD",
    "AMEX": "USD",
}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("malformed numeric tick value") from exc


def _timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000
        parsed = datetime.fromtimestamp(raw, tz=timezone.utc)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class LiveTickAdapter:
    def normalize(self, tick: dict[str, Any]) -> MarketTick:
        raw_symbol = str(tick.get("symbol") or tick.get("instrument") or "").strip().upper()
        if not raw_symbol:
            raise ValueError("tick symbol is required")
        if ":" in raw_symbol:
            venue, symbol = raw_symbol.split(":", 1)
        else:
            venue, symbol = "NSE", raw_symbol
        if venue not in VENUE_CURRENCIES:
            raise ValueError(f"unknown explicit venue: {venue}")
        price = _decimal(
            tick.get("ltp", tick.get("last_price", tick.get("price", tick.get("c"))))
        )
        if price is None:
            raise ValueError("tick price is required")
        instrument = InstrumentId(
            symbol=symbol,
            venue=venue,
            asset_class="EQUITY",
            currency=VENUE_CURRENCIES[venue],
        )
        return MarketTick(
            instrument=instrument,
            ts=_timestamp(tick.get("timestamp", tick.get("ts", tick.get("time")))),
            price=price,
            size=_decimal(tick.get("size", tick.get("volume"))),
            bid=_decimal(tick.get("bid")),
            ask=_decimal(tick.get("ask")),
            source=str(tick.get("source") or tick.get("provider") or "live").strip() or None,
        )


def instrument_from_legacy_symbol(value: str) -> InstrumentId:
    raw = value.strip().upper()
    if not raw:
        raise ValueError("symbol is required")
    if ":" in raw:
        venue, symbol = raw.split(":", 1)
    else:
        venue, symbol = "NSE", raw
    if venue not in VENUE_CURRENCIES:
        raise ValueError(f"unknown explicit venue: {venue}")
    return InstrumentId(symbol=symbol, venue=venue, asset_class="EQUITY", currency=VENUE_CURRENCIES[venue])

