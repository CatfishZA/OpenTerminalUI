from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from backend.services.corp_actions_service import list_actions
from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import CorporateActionType
from backend.simulation.domain.identifiers import InstrumentId


class CorporateActionsAdapter:
    def __init__(self, db: Session):
        self.db = db

    def events(
        self,
        instruments: list[InstrumentId],
        start: date,
        end: date,
        data_version_id: str,
    ) -> Iterable[CorporateAction]:
        converted: list[CorporateAction] = []
        for instrument in instruments:
            for row in list_actions(self.db, instrument.symbol, data_version_id):
                action_date = date.fromisoformat(row.action_date)
                if action_date < start or action_date > end:
                    continue
                if row.data_version_id not in {None, data_version_id}:
                    continue
                raw_type = row.action_type.strip().upper()
                if raw_type in {"SPLIT", "STOCK_SPLIT"}:
                    action_type = CorporateActionType.SPLIT
                elif raw_type in {"DIVIDEND", "CASH_DIVIDEND"}:
                    action_type = CorporateActionType.CASH_DIVIDEND
                else:
                    continue
                converted.append(
                    CorporateAction(
                        id=row.id,
                        instrument=instrument,
                        action_type=action_type,
                        ex_date=action_date,
                        record_date=None,
                        pay_date=action_date,
                        factor=Decimal(str(row.factor)) if action_type is CorporateActionType.SPLIT else None,
                        cash_amount=Decimal(str(row.amount)) if row.amount is not None else None,
                        currency=instrument.currency if action_type is CorporateActionType.CASH_DIVIDEND else None,
                        data_version_id=row.data_version_id or data_version_id,
                    )
                )
        return iter(sorted(converted, key=lambda item: (item.ex_date, item.instrument.key, item.id)))
