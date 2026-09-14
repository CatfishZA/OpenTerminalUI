from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from backend.services.price_series_service import PricePoint, get_price_series
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import MarketBar, MarketDataManifest
from backend.models import PriceEodORM
from backend.simulation.services.market_data_integrity_service import MarketDataIntegrityService


class VersionedDataAdapter:
    """Reads persisted versioned EOD rows without provider or venue fallback."""

    def __init__(
        self,
        db: Session,
        *,
        data_version_id: str | None,
        instruments: list[InstrumentId],
        start: date,
        end: date,
        dataset_hash: str | None = None,
        calendar_version: str | None = None,
    ):
        self.db = db
        self.data_version_id = data_version_id
        self.instruments = list(instruments)
        self.start = start
        self.end = end
        self.dataset_hash = dataset_hash
        self.calendar_version = calendar_version

    def manifest(self) -> MarketDataManifest:
        return MarketDataManifest(
            data_version_id=self.data_version_id,
            dataset_hash=self.dataset_hash,
            instruments=tuple(self.instruments),
            start=self.start,
            end=self.end,
            data_source="persisted_versioned_prices",
            adjusted=False,
            calendar_version=self.calendar_version,
            corporate_action_version=self.data_version_id,
        )

    async def load_series(self, instrument: InstrumentId, fetcher: object | None = None) -> list[PricePoint]:
        """Use the existing price-series service in its strict persisted mode."""
        if not self.data_version_id:
            raise ValueError("DATA_VERSION_REQUIRED: persisted versioned data requires data_version_id")
        _version, points = await get_price_series(
            self.db,
            fetcher,
            instrument.symbol,
            adjusted=False,
            start=self.start.isoformat(),
            end=self.end.isoformat(),
            data_version_id=self.data_version_id,
            strict_persisted=True,
        )
        return points

    def iter_daily_events(
        self, instruments: list[InstrumentId], start: date, end: date
    ) -> Iterable[MarketBar]:
        if not self.data_version_id:
            raise ValueError("DATA_VERSION_REQUIRED: persisted versioned data requires data_version_id")
        requested = {item.key: item for item in instruments}
        events: list[MarketBar] = []
        for instrument in sorted(instruments, key=lambda item: item.key):
            rows = self.db.query(PriceEodORM).filter(
                PriceEodORM.symbol == instrument.symbol,
                PriceEodORM.data_version_id == self.data_version_id,
                PriceEodORM.trade_date >= start.isoformat(),
                PriceEodORM.trade_date <= end.isoformat(),
            ).order_by(PriceEodORM.trade_date).all()
            if not rows:
                raise ValueError(f"INSTRUMENT_DATA_NOT_FOUND: {instrument.key}")
            for row in rows:
                session = date.fromisoformat(row.trade_date)
                MarketDataIntegrityService.validate_bar_values(
                    open_price=row.open, high=row.high, low=row.low, close=row.close,
                    volume=row.volume, instrument=instrument.key, session=row.trade_date,
                )
                events.append(MarketBar(
                    instrument=instrument,
                    ts_open=datetime.combine(session, time(14, 30), timezone.utc),
                    ts_close=datetime.combine(session, time(21, 0), timezone.utc),
                    open=Decimal(str(row.open)), high=Decimal(str(row.high)),
                    low=Decimal(str(row.low)), close=Decimal(str(row.close)),
                    volume=Decimal(str(row.volume)), data_version_id=self.data_version_id,
                ))
        return sorted(events, key=lambda item: (item.ts_open, item.instrument.key))
