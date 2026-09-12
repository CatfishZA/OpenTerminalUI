from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from backend.services.price_series_service import PricePoint, get_price_series
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import MarketBar, MarketDataManifest


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
        raise NotImplementedError(
            "Calendar-resolved market event timestamps are intentionally deferred to Phase 1B; use load_series in Phase 1A"
        )
