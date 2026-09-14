from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.corporate_actions import CorporateAction, DividendEntitlement
from backend.simulation.domain.enums import CorporateActionType, LedgerEntryType, OrderSide
from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.orders import Order


@dataclass(frozen=True, slots=True)
class CorporateActionApplicationResult:
    applied: tuple[dict, ...]
    adjusted_orders: tuple[Order, ...]
    entitlements_created: tuple[DividendEntitlement, ...]
    entitlements_paid: tuple[DividendEntitlement, ...]
    ledger_entries: tuple[LedgerEntry, ...]


class CorporateActionEngine:
    """Canonical Decimal accounting for daily split and dividend events."""

    def apply_session_actions(
        self,
        account: AccountState,
        actions: Iterable[CorporateAction],
        session: date,
        *,
        run_id: str,
        at: datetime,
        open_orders: dict[str, Order],
        applied_action_ids: set[str],
        entitlements: list[DividendEntitlement],
    ) -> CorporateActionApplicationResult:
        applied: list[dict] = []
        adjusted_orders: list[Order] = []
        created: list[DividendEntitlement] = []
        paid: list[DividendEntitlement] = []
        ledger: list[LedgerEntry] = []

        action_priority = {
            CorporateActionType.SPLIT: 0,
            CorporateActionType.CASH_DIVIDEND: 1,
        }
        for action in sorted(
            actions,
            key=lambda item: (item.instrument.key, action_priority[item.action_type], item.id),
        ):
            if action.ex_date != session or action.id in applied_action_ids:
                continue
            if action.action_type is CorporateActionType.SPLIT:
                payload, changed = self._apply_split(account, action, open_orders)
                adjusted_orders.extend(changed)
            elif action.action_type is CorporateActionType.CASH_DIVIDEND:
                payload, entitlement = self._establish_dividend(account, action, run_id, at)
                entitlements.append(entitlement)
                created.append(entitlement)
            else:  # pragma: no cover - adapter rejects unsupported actions
                raise ValueError(f"CORPORATE_ACTION_UNSUPPORTED: {action.action_type}")
            applied_action_ids.add(action.id)
            applied.append(payload)

        for index, entitlement in enumerate(tuple(entitlements)):
            if entitlement.status != "PENDING" or entitlement.pay_date > session:
                continue
            cash = account.base_cash
            account.cash[account.base_currency] = replace(cash, settled=cash.settled + entitlement.total_amount)
            account.buying_power = account.base_cash.available
            account.equity += entitlement.total_amount
            paid_item = replace(entitlement, status="PAID", paid_at=at)
            entitlements[index] = paid_item
            paid.append(paid_item)
            if entitlement.total_amount != 0:
                ledger.append(LedgerEntry(
                    id=f"led_{run_id}_{entitlement.corporate_action_source_id}_dividend",
                    run_id=run_id,
                    account_id=account.account_id,
                    ts=at,
                    entry_type=LedgerEntryType.DIVIDEND,
                    currency=entitlement.currency,
                    amount=entitlement.total_amount,
                    instrument=entitlement.instrument,
                    corporate_action_id=entitlement.corporate_action_source_id,
                    metadata={"entitlement_id": entitlement.id, "pay_date": entitlement.pay_date.isoformat()},
                ))

        return CorporateActionApplicationResult(
            tuple(applied), tuple(adjusted_orders), tuple(created), tuple(paid), tuple(ledger)
        )

    @staticmethod
    def _apply_split(
        account: AccountState,
        action: CorporateAction,
        open_orders: dict[str, Order],
    ) -> tuple[dict, list[Order]]:
        assert action.factor is not None
        factor = action.factor
        position = account.positions.get(action.instrument)
        old_quantity = position.quantity if position else Decimal(0)
        old_average = position.average_cost if position else Decimal(0)
        new_quantity = old_quantity * factor
        new_average = old_average / factor if old_quantity else old_average
        if position is not None:
            account.positions[action.instrument] = replace(
                position,
                quantity=new_quantity,
                average_cost=new_average,
                last_mark=position.last_mark / factor if position.last_mark is not None else None,
                market_value=position.market_value,
            )
        changed: list[Order] = []
        for order_id, order in sorted(tuple(open_orders.items())):
            if order.instrument != action.instrument:
                continue
            adjusted = replace(
                order,
                quantity=order.quantity * factor,
                remaining_quantity=order.remaining_quantity * factor,
                limit_price=order.limit_price / factor if order.limit_price is not None else None,
                stop_price=order.stop_price / factor if order.stop_price is not None else None,
            )
            # BUY reservation is already an economic cash amount, so it remains
            # unchanged while quantity and reference price move inversely.
            open_orders[order_id] = adjusted
            account.open_orders[order_id] = adjusted
            changed.append(adjusted)
        return ({
            "source_action_id": action.id,
            "instrument": action.instrument.key,
            "action_type": action.action_type.value,
            "factor": str(factor),
            "old_quantity": str(old_quantity),
            "new_quantity": str(new_quantity),
            "old_average_cost": str(old_average),
            "new_average_cost": str(new_average),
            "adjusted_open_order_ids": [order.id for order in changed],
        }, changed)

    @staticmethod
    def _establish_dividend(
        account: AccountState,
        action: CorporateAction,
        run_id: str,
        at: datetime,
    ) -> tuple[dict, DividendEntitlement]:
        assert action.cash_amount is not None and action.currency and action.pay_date
        position = account.positions.get(action.instrument)
        eligible = position.quantity if position else Decimal(0)
        total = eligible * action.cash_amount
        entitlement = DividendEntitlement(
            id=f"caent_{run_id[4:]}_{action.id}",
            run_id=run_id,
            corporate_action_source_id=action.id,
            instrument=action.instrument,
            entitlement_date=action.ex_date,
            pay_date=action.pay_date,
            eligible_quantity=eligible,
            cash_amount_per_share=action.cash_amount,
            currency=action.currency,
            total_amount=total,
            created_at=at,
        )
        return ({
            "source_action_id": action.id,
            "instrument": action.instrument.key,
            "action_type": action.action_type.value,
            "eligible_quantity": str(eligible),
            "cash_amount_per_share": str(action.cash_amount),
            "total_amount": str(total),
            "pay_date": action.pay_date.isoformat(),
            "payment_status": "PENDING",
        }, entitlement)
