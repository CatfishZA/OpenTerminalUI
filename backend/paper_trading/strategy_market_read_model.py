from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import PaperStrategyInputORM, PriceEodORM
from backend.paper_trading.deployment_domain import CompletedBarObservation
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import MarketBar


class DeploymentMarketReadModel:
    """Point-in-time history from approved persisted data plus accepted forward bars."""

    def __init__(
        self,
        db: Session,
        *,
        deployment_id: str,
        data_version_id: str,
        instruments: tuple[InstrumentId, ...],
        decision_time: datetime,
    ):
        self._history: dict[InstrumentId, tuple[MarketBar, ...]] = {}
        for instrument in instruments:
            bars = self._persisted(db, data_version_id, instrument, decision_time)
            bars.extend(self._forward(db, deployment_id, instrument, decision_time))
            unique = {(bar.ts_close, bar.instrument.key): bar for bar in bars}
            self._history[instrument] = tuple(sorted(unique.values(), key=lambda bar: bar.ts_close))

    def history(self, instrument: InstrumentId, *, limit: int) -> tuple[MarketBar, ...]:
        rows = self._history.get(instrument, ())
        return rows[-max(0, limit):] if limit else ()

    @staticmethod
    def _persisted(db: Session, version: str, instrument: InstrumentId, before: datetime) -> list[MarketBar]:
        rows = db.query(PriceEodORM).filter(
            PriceEodORM.symbol == instrument.symbol,
            PriceEodORM.data_version_id == version,
            PriceEodORM.trade_date < before.date().isoformat(),
        ).order_by(PriceEodORM.trade_date).all()
        result = []
        for row in rows:
            session = date.fromisoformat(row.trade_date)
            result.append(MarketBar(
                instrument=instrument,
                ts_open=datetime.combine(session, time(14, 30), timezone.utc),
                ts_close=datetime.combine(session, time(21, 0), timezone.utc),
                open=Decimal(str(row.open)), high=Decimal(str(row.high)),
                low=Decimal(str(row.low)), close=Decimal(str(row.close)),
                volume=Decimal(str(row.volume)), data_version_id=version,
            ))
        return result

    @staticmethod
    def _forward(db: Session, deployment_id: str, instrument: InstrumentId, through: datetime) -> list[MarketBar]:
        rows = db.query(PaperStrategyInputORM).filter(
            PaperStrategyInputORM.deployment_id == deployment_id,
            PaperStrategyInputORM.instrument_key == instrument.key,
            PaperStrategyInputORM.input_time <= through,
            PaperStrategyInputORM.processed_status.in_(["PROCESSING", "PROCESSED", "NO_INTENT"]),
        ).order_by(PaperStrategyInputORM.input_time, PaperStrategyInputORM.accepted_sequence).all()
        result = []
        for row in rows:
            raw = dict(row.payload_json or {})
            result.append(MarketBar(
                instrument=instrument,
                ts_open=datetime.fromisoformat(raw["start_time"]),
                ts_close=datetime.fromisoformat(raw["end_time"]),
                open=Decimal(raw["open"]), high=Decimal(raw["high"]),
                low=Decimal(raw["low"]), close=Decimal(raw["close"]),
                volume=Decimal(raw["volume"]), data_version_id=f"paper:{deployment_id}",
            ))
        return result


def observation_payload(item: CompletedBarObservation) -> dict[str, str | bool]:
    return {
        "source_event_id": item.source_event_id,
        "instrument": item.instrument.key,
        "interval": item.interval,
        "start_time": item.start_time.isoformat(),
        "end_time": item.end_time.isoformat(),
        "open": str(item.open), "high": str(item.high), "low": str(item.low),
        "close": str(item.close), "volume": str(item.volume),
        "source": item.source,
        "complete": item.complete,
    }
