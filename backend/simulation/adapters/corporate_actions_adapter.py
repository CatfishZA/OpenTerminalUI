from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from backend.models import CorpActionORM
from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import CorporateActionType, VerificationLevel
from backend.simulation.domain.identifiers import InstrumentId


class CorporateActionsAdapter:
    """Deterministic, version-aware translation of persisted corporate actions."""

    def __init__(self, db: Session):
        self.db = db

    def events(
        self,
        instruments: list[InstrumentId],
        start: date,
        end: date,
        data_version_id: str,
        *,
        verification_level: VerificationLevel = VerificationLevel.RESEARCH,
    ) -> Iterable[CorporateAction]:
        converted: list[CorporateAction] = []
        for instrument in sorted(instruments, key=lambda item: item.key):
            rows = self.db.query(CorpActionORM).filter(
                CorpActionORM.symbol == instrument.symbol,
                (CorpActionORM.data_version_id == data_version_id) | (CorpActionORM.data_version_id.is_(None)),
            ).order_by(CorpActionORM.action_date, CorpActionORM.id).all()
            for row in rows:
                raw_type = row.action_type.strip().upper()
                if raw_type in {"SPLIT", "STOCK_SPLIT"}:
                    action_type = CorporateActionType.SPLIT
                elif raw_type in {"DIVIDEND", "CASH_DIVIDEND"}:
                    action_type = CorporateActionType.CASH_DIVIDEND
                else:
                    if verification_level is VerificationLevel.VERIFIED:
                        raise ValueError(f"CORPORATE_ACTION_UNSUPPORTED: {row.id} type={raw_type}")
                    continue
                warnings: list[str] = []
                if row.data_version_id is None:
                    if verification_level is VerificationLevel.VERIFIED:
                        raise ValueError(f"CORPORATE_ACTION_VERSION_MISMATCH: {row.id} is unversioned")
                    warnings.append("LEGACY_UNVERSIONED_CORPORATE_ACTION")
                try:
                    legacy_date = date.fromisoformat(row.action_date)
                    explicit_ex = date.fromisoformat(row.ex_date) if row.ex_date else None
                    record_date = date.fromisoformat(row.record_date) if row.record_date else None
                    pay_date = date.fromisoformat(row.pay_date) if row.pay_date else None
                except ValueError as exc:
                    raise ValueError(f"CORPORATE_ACTION_DATE_INCOMPLETE: {row.id}") from exc
                ex_date = explicit_ex or legacy_date
                if action_type is CorporateActionType.CASH_DIVIDEND:
                    if verification_level is VerificationLevel.VERIFIED and (explicit_ex is None or pay_date is None):
                        raise ValueError(f"CORPORATE_ACTION_DATE_INCOMPLETE: {row.id}")
                    if pay_date is None:
                        pay_date = legacy_date
                        warnings.append("LEGACY_DIVIDEND_DATE_ASSUMPTION")
                    currency = row.currency or (instrument.currency if verification_level is VerificationLevel.RESEARCH else None)
                    if row.amount is None or Decimal(str(row.amount)) < 0 or not currency:
                        raise ValueError(f"CORPORATE_ACTION_INVALID: {row.id} dividend amount/currency")
                    factor = None
                    cash_amount = Decimal(str(row.amount))
                else:
                    factor = Decimal(str(row.factor))
                    if factor <= 0:
                        raise ValueError(f"CORPORATE_ACTION_INVALID: {row.id} split factor")
                    cash_amount = None
                    currency = None
                    pay_date = None
                if ex_date < start or ex_date > end:
                    continue
                converted.append(CorporateAction(
                    id=row.id, instrument=instrument, action_type=action_type,
                    ex_date=ex_date, record_date=record_date, pay_date=pay_date,
                    factor=factor, cash_amount=cash_amount,
                    currency=currency.upper() if currency else None,
                    data_version_id=row.data_version_id,
                    warnings=tuple(sorted(set(warnings))), source=row.source,
                    metadata=dict(row.metadata_json or {}),
                ))
        return iter(sorted(converted, key=lambda item: (item.ex_date, item.instrument.key, item.id)))
