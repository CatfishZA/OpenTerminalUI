from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date

from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal
from backend.simulation.domain.orders import Order
from backend.simulation.domain.positions import Position


@dataclass(frozen=True, slots=True)
class SettlementObligation:
    settlement_date: date
    currency: str
    amount: Decimal
    fill_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", as_decimal(self.amount, "amount"))


@dataclass(slots=True)
class AccountState:
    account_id: str
    base_currency: str
    cash: dict[str, CashBalance] = field(default_factory=dict)
    positions: dict[InstrumentId, Position] = field(default_factory=dict)
    open_orders: dict[str, Order] = field(default_factory=dict)
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    buying_power: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    settlements: list[SettlementObligation] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base_currency = self.base_currency.strip().upper()
        if not self.account_id or len(self.base_currency) != 3:
            raise ValueError("account id and three-letter base currency are required")
        for name in ("realized_pnl", "unrealized_pnl", "equity", "buying_power", "fees"):
            setattr(self, name, as_decimal(getattr(self, name), name))

    @property
    def base_cash(self) -> CashBalance:
        return self.cash.get(self.base_currency, CashBalance(self.base_currency))
