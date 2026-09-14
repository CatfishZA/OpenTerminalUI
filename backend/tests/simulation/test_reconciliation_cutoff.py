from __future__ import annotations

import asyncio
from datetime import timedelta

from backend.simulation.domain.reconciliation import BacktestPaperReconciliationSpec
from backend.simulation.persistence.models import SimulationEventORM, SimulationOrderORM
from backend.simulation.services.backtest_paper_reconciliation_service import BacktestPaperReconciliationService
from backend.tests.simulation.reconciliation_test_helpers import INSTRUMENT, NOW, canonical_pair


def test_historical_report_does_not_change_after_later_paper_activity(db_session) -> None:  # noqa: ANN001
    baseline, paper, cutoff = canonical_pair(db_session)
    service = BacktestPaperReconciliationService(db_session)
    first = asyncio.run(service.create(BacktestPaperReconciliationSpec(baseline.id, paper.id, paper_cutoff_sequence=cutoff)))
    paper_order = db_session.get(SimulationOrderORM, "ord_paper")
    paper_order.status = "CANCELLED"
    db_session.add(
        SimulationEventORM(
            run_id=paper.id, sequence=cutoff + 1, event_id="evt:later", event_type="ORDER_CANCELLED",
            event_time=NOW + timedelta(minutes=1), processing_time=NOW + timedelta(minutes=1),
            instrument_key=INSTRUMENT, order_id=paper_order.id, payload_json={},
        )
    )
    db_session.commit()
    stored = service.get(first["reconciliation_id"])
    assert stored == first
    assert stored["report_hash"] == first["report_hash"]
    later = asyncio.run(service.create(BacktestPaperReconciliationSpec(baseline.id, paper.id)))
    assert later["reconciliation_id"] != first["reconciliation_id"]
    assert later["paper_cutoff_sequence"] == cutoff + 1


def test_historical_cutoff_does_not_leak_later_mutable_order_state(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session)
    report = asyncio.run(
        BacktestPaperReconciliationService(db_session).create(
            BacktestPaperReconciliationSpec(baseline.id, paper.id, paper_cutoff_sequence=2)
        )
    )
    item = report["items"][0]
    assert item["metrics"]["paper"]["order"]["status"] == "ACCEPTED"
    assert item["metrics"]["paper"]["order"]["completed_at"] is None
    assert item["metrics"]["paper"]["fills"]["fill_count"] == 0
