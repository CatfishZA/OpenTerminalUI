import { useEffect, useMemo, useState } from "react";

import {
  fetchSimulationEvents,
  fetchSimulationFills,
  fetchSimulationLedger,
  fetchSimulationOrders,
  type SimulationEvent,
  type SimulationFill,
  type SimulationLedgerEntry,
  type SimulationOrder,
} from "../../api/client";

type Tab = "orders" | "fills" | "ledger" | "events";
type Artifact = SimulationOrder | SimulationFill | SimulationLedgerEntry | SimulationEvent;
type State = { items: Artifact[]; loading: boolean; loaded: boolean; error: string | null };

const EMPTY: State = { items: [], loading: false, loaded: false, error: null };
const TABS: Array<{ key: Tab; label: string }> = [
  { key: "orders", label: "Orders" }, { key: "fills", label: "Fills" },
  { key: "ledger", label: "Ledger" }, { key: "events", label: "Events" },
];

const display = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number" && !Number.isFinite(value)) return "—";
  return String(value);
};
const time = (value: unknown): string => value ? display(value) : "—";

export function ExecutionArtifactsPanel({ simulationRunId }: { simulationRunId: string }) {
  const [tab, setTab] = useState<Tab>("orders");
  const [states, setStates] = useState<Record<Tab, State>>({ orders: EMPTY, fills: EMPTY, ledger: EMPTY, events: EMPTY });
  const [attempt, setAttempt] = useState(0);
  const state = states[tab];

  useEffect(() => {
    if (state.loaded || state.loading) return;
    let active = true;
    setStates((current) => ({ ...current, [tab]: { ...current[tab], loading: true, error: null } }));
    const request = tab === "orders" ? fetchSimulationOrders(simulationRunId, { limit: 100 })
      : tab === "fills" ? fetchSimulationFills(simulationRunId, { limit: 100 })
        : tab === "ledger" ? fetchSimulationLedger(simulationRunId, { limit: 100 })
          : fetchSimulationEvents(simulationRunId, { limit: 100 });
    void request.then((response) => {
      if (!active) return;
      setStates((current) => ({ ...current, [tab]: { items: response.items || [], loading: false, loaded: true, error: null } }));
    }).catch((error: unknown) => {
      if (!active) return;
      setStates((current) => ({ ...current, [tab]: { items: [], loading: false, loaded: false, error: error instanceof Error ? error.message : `Unable to load ${tab}` } }));
    });
    return () => { active = false; };
  }, [attempt, simulationRunId, tab]);

  const items = useMemo(() => tab === "events"
    ? [...state.items].sort((a, b) => Number((a as SimulationEvent).sequence) - Number((b as SimulationEvent).sequence))
    : state.items, [state.items, tab]);

  const retry = () => {
    setStates((current) => ({ ...current, [tab]: { ...EMPTY } }));
    setAttempt((value) => value + 1);
  };

  return (
    <section aria-label="Canonical execution artifacts" className="rounded border border-terminal-border/60 bg-terminal-panel p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div><h3 className="text-xs font-semibold uppercase tracking-wide text-terminal-text">Canonical Execution Artifacts</h3><p className="text-[10px] text-terminal-muted">Evidence from {simulationRunId}</p></div>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Execution artifacts">
          {TABS.map((item) => <button key={item.key} type="button" role="tab" aria-selected={tab === item.key} onClick={() => setTab(item.key)} className={`rounded border px-2 py-1 text-[11px] focus:outline-none focus:ring-2 focus:ring-terminal-accent ${tab === item.key ? "border-terminal-accent bg-terminal-accent/10 text-terminal-accent" : "border-terminal-border text-terminal-muted"}`}>{item.label}</button>)}
        </div>
      </div>
      {state.loading ? <p className="py-5 text-center text-xs text-terminal-muted">Loading {tab}…</p> : null}
      {state.error ? <div role="alert" className="rounded border border-terminal-neg/60 bg-terminal-neg/10 p-2 text-xs text-terminal-neg"><p>{state.error}</p><button type="button" onClick={retry} className="mt-2 rounded border border-terminal-neg px-2 py-1 font-semibold">Retry</button></div> : null}
      {!state.loading && !state.error && state.loaded && items.length === 0 ? <p className="py-5 text-center text-xs text-terminal-muted">No {tab} recorded.</p> : null}
      {!state.loading && !state.error && items.length > 0 ? <div className="max-w-full overflow-x-auto">{tab === "orders" ? <OrdersTable items={items as SimulationOrder[]} /> : tab === "fills" ? <FillsTable items={items as SimulationFill[]} /> : tab === "ledger" ? <LedgerTable items={items as SimulationLedgerEntry[]} /> : <EventsTable items={items as SimulationEvent[]} />}</div> : null}
    </section>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: Array<Array<unknown>> }) {
  return <table className="min-w-max text-[11px]"><thead><tr className="border-b border-terminal-border text-terminal-muted">{headers.map((header) => <th key={header} scope="col" className="whitespace-nowrap px-2 py-1 text-left">{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} className="border-b border-terminal-border/30 text-terminal-text">{row.map((value, cell) => <td key={cell} className="max-w-80 whitespace-nowrap px-2 py-1 font-mono" title={display(value)}>{display(value)}</td>)}</tr>)}</tbody></table>;
}

const OrdersTable = ({ items }: { items: SimulationOrder[] }) => <Table headers={["Order ID", "Instrument", "Side", "Type", "Quantity", "Remaining", "TIF", "Status", "Submitted", "Accepted", "Completed", "Limit", "Stop"]} rows={items.map((x) => [x.id, x.instrument_key, x.side, x.order_type, x.quantity, x.remaining_quantity, x.tif, x.status, time(x.submitted_at), time(x.accepted_at), time(x.completed_at), x.limit_price, x.stop_price])} />;
const FillsTable = ({ items }: { items: SimulationFill[] }) => <Table headers={["Fill ID", "Order ID", "Instrument", "Side", "Quantity", "Price", "Commission", "Fees", "Slippage BPS", "Execution Model", "Executed At"]} rows={items.map((x) => [x.id, x.order_id, x.instrument_key, x.side, x.quantity, x.price, x.commission, x.fees, x.slippage_bps, x.execution_model, time(x.executed_at)])} />;
const LedgerTable = ({ items }: { items: SimulationLedgerEntry[] }) => <Table headers={["Time", "Type", "Direction", "Currency", "Amount", "Instrument", "Order ID", "Fill ID"]} rows={items.map((x) => [time(x.event_time), x.entry_type, Number(x.amount) < 0 ? "Outflow" : "Inflow", x.currency, x.amount, x.instrument_key, x.order_id, x.fill_id])} />;
const EventsTable = ({ items }: { items: SimulationEvent[] }) => <Table headers={["Sequence", "Event Time", "Event Type", "Instrument", "Order ID", "Fill ID", "Payload"]} rows={items.map((x) => [x.sequence, time(x.event_time), x.event_type, x.instrument_key, x.order_id, x.fill_id, x.payload_json ? JSON.stringify(x.payload_json) : "—"])} />;
