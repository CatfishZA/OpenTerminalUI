import { useEffect, useMemo, useState } from "react";
import { PlusIcon, WrenchScrewdriverIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { createPaperPortfolio, fetchPaperOrders, fetchPaperPerformance, fetchPaperPortfolios, fetchPaperPositions, fetchPaperTrades, placePaperOrder } from "../api/client";
import { HotKeyPanel } from "../components/trading/HotKeyPanel";

type Tab = "positions" | "orders" | "trades" | "performance";
const fieldClass = "mt-1.5 h-10 w-full rounded-md border border-terminal-border bg-terminal-bg px-3 text-sm text-terminal-text";
const money = (value?: number | null) => Number(value ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function Kpi({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return <article className="rounded-lg border border-terminal-border bg-terminal-panel p-4"><p className="text-sm text-terminal-muted">{label}</p><p className={`mt-3 ot-type-data text-xl font-semibold ${tone || "text-terminal-text"}`}>{value}</p></article>;
}

export function ProductPaperTradingPage() {
  const [portfolios, setPortfolios] = useState<Array<{ id: string; name: string; initial_capital: number; current_cash: number }>>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState("");
  const [name, setName] = useState("Paper Portfolio");
  const [capital, setCapital] = useState(100000);
  const [symbol, setSymbol] = useState("NSE:RELIANCE");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit" | "sl">("market");
  const [quantity, setQuantity] = useState(1);
  const [limitPrice, setLimitPrice] = useState(0);
  const [slPrice, setSlPrice] = useState(0);
  const [positions, setPositions] = useState<Array<{ id: string; symbol: string; quantity: number; avg_entry_price: number; mark_price: number; unrealized_pnl: number }>>([]);
  const [orders, setOrders] = useState<Array<{ id: string; symbol: string; side: string; order_type: string; quantity: number; status: string }>>([]);
  const [trades, setTrades] = useState<Array<{ id: string; symbol: string; side: string; quantity: number; price: number; timestamp: string; pnl_realized?: number | null }>>([]);
  const [perf, setPerf] = useState<{ equity?: number; pnl?: number; cumulative_return?: number; sharpe_ratio?: number; max_drawdown?: number } | null>(null);
  const [tab, setTab] = useState<Tab>("positions");
  const [createOpen, setCreateOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPortfolios() {
    const items = await fetchPaperPortfolios();
    setPortfolios(items);
    if (!selectedPortfolioId && items.length) setSelectedPortfolioId(items[0].id);
  }
  async function loadDetails(id: string) {
    if (!id) return;
    const [nextPositions, nextOrders, nextTrades, performance] = await Promise.all([fetchPaperPositions(id), fetchPaperOrders(id), fetchPaperTrades(id), fetchPaperPerformance(id)]);
    setPositions(nextPositions); setOrders(nextOrders); setTrades(nextTrades); setPerf(performance);
  }
  useEffect(() => { void loadPortfolios(); }, []);
  useEffect(() => { if (selectedPortfolioId) void loadDetails(selectedPortfolioId); }, [selectedPortfolioId]);

  const selected = useMemo(() => portfolios.find((portfolio) => portfolio.id === selectedPortfolioId) ?? null, [portfolios, selectedPortfolioId]);
  const pnl = Number(perf?.pnl ?? 0);
  const openOrders = orders.filter((order) => !["filled", "cancelled", "canceled", "rejected"].includes(order.status.toLowerCase())).length;
  const unrealized = positions.reduce((sum, position) => sum + position.unrealized_pnl, 0);

  const placeOrder = () => {
    if (!selectedPortfolioId) { setError("Select portfolio first"); return; }
    void (async () => {
      try {
        await placePaperOrder({ portfolio_id: selectedPortfolioId, symbol, side, order_type: orderType, quantity, limit_price: orderType === "limit" ? limitPrice : undefined, sl_price: orderType === "sl" ? slPrice : undefined });
        await loadDetails(selectedPortfolioId); setError(null);
      } catch (reason) { setError(reason instanceof Error ? reason.message : "Failed to place order"); }
    })();
  };

  return (
    <main className="mx-auto w-full max-w-[1480px] space-y-6 p-4 md:p-6 lg:p-8" aria-labelledby="paper-title">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div><p className="text-sm font-medium text-terminal-accent">Trading</p><h1 id="paper-title" className="mt-1 text-2xl font-semibold text-terminal-text">Paper trading</h1><p className="mt-2 text-sm text-terminal-muted">Practice execution with virtual capital and the existing paper ledger.</p></div>
        <div className="flex flex-wrap gap-2"><select aria-label="Portfolio" className="h-10 min-w-48 rounded-md border border-terminal-border bg-terminal-panel px-3 text-sm text-terminal-text" value={selectedPortfolioId} onChange={(event) => setSelectedPortfolioId(event.target.value)}><option value="">Select portfolio</option>{portfolios.map((portfolio) => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}</select><button type="button" onClick={() => setCreateOpen(true)} className="inline-flex h-10 items-center gap-2 rounded-md bg-terminal-accent px-4 text-sm font-semibold text-black"><PlusIcon className="h-4 w-4" />New portfolio</button></div>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Paper portfolio summary"><Kpi label="Equity" value={selected ? money(perf?.equity) : "—"} /><Kpi label="Cash" value={selected ? money(selected.current_cash) : "—"} /><Kpi label="Total P&L" value={selected ? money(pnl) : "—"} tone={!selected ? "" : pnl >= 0 ? "text-terminal-pos" : "text-terminal-neg"} /><Kpi label="Open Orders" value={String(openOrders)} /></section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <section className="rounded-lg border border-terminal-border bg-terminal-panel p-5" aria-labelledby="order-entry-title">
          <div className="flex items-center justify-between"><div><h2 id="order-entry-title" className="font-semibold text-terminal-text">Order entry</h2><p className="mt-1 text-xs text-terminal-muted">Orders use the selected virtual portfolio.</p></div><button type="button" onClick={() => setToolsOpen((open) => !open)} className="inline-flex items-center gap-2 rounded-md border border-terminal-border px-3 py-2 text-xs text-terminal-muted hover:text-terminal-text" aria-expanded={toolsOpen}><WrenchScrewdriverIcon className="h-4 w-4" />Trading tools</button></div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><label className="text-xs text-terminal-muted">Instrument<input aria-label="Instrument" className={`${fieldClass} uppercase`} value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} /></label><label className="text-xs text-terminal-muted">Side<select aria-label="Side" className={fieldClass} value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")}><option value="buy">Buy</option><option value="sell">Sell</option></select></label><label className="text-xs text-terminal-muted">Order type<select aria-label="Order type" className={fieldClass} value={orderType} onChange={(event) => setOrderType(event.target.value as "market" | "limit" | "sl")}><option value="market">Market</option><option value="limit">Limit</option><option value="sl">Stop loss</option></select></label><label className="text-xs text-terminal-muted">Quantity<input aria-label="Quantity" className={fieldClass} type="number" min={1} value={quantity} onChange={(event) => setQuantity(Math.max(1, Number(event.target.value)))} /></label>{orderType === "limit" ? <label className="text-xs text-terminal-muted">Limit price<input aria-label="Limit price" className={fieldClass} type="number" value={limitPrice} onChange={(event) => setLimitPrice(Number(event.target.value))} /></label> : null}{orderType === "sl" ? <label className="text-xs text-terminal-muted">Stop price<input aria-label="Stop price" className={fieldClass} type="number" value={slPrice} onChange={(event) => setSlPrice(Number(event.target.value))} /></label> : null}</div>
          <button type="button" onClick={placeOrder} className="mt-5 h-10 rounded-md bg-terminal-accent px-5 text-sm font-semibold text-black">Place {side} order</button>{error ? <p role="alert" className="mt-4 rounded-md border border-terminal-neg/50 bg-terminal-neg/10 p-3 text-sm text-terminal-neg">{error}</p> : null}
        </section>
        <section className="rounded-lg border border-terminal-border bg-terminal-panel p-5" aria-labelledby="position-summary"><h2 id="position-summary" className="font-semibold text-terminal-text">Positions summary</h2><dl className="mt-5 space-y-4 text-sm"><div className="flex justify-between"><dt className="text-terminal-muted">Open positions</dt><dd className="ot-type-data">{positions.length}</dd></div><div className="flex justify-between"><dt className="text-terminal-muted">Unrealized P&L</dt><dd className={`ot-type-data ${unrealized >= 0 ? "text-terminal-pos" : "text-terminal-neg"}`}>{money(unrealized)}</dd></div><div className="flex justify-between"><dt className="text-terminal-muted">Return</dt><dd className="ot-type-data">{(Number(perf?.cumulative_return ?? 0) * 100).toFixed(2)}%</dd></div></dl></section>
      </div>
      {toolsOpen ? <HotKeyPanel embedded /> : null}

      <section className="overflow-hidden rounded-lg border border-terminal-border bg-terminal-panel">
        <div className="flex overflow-x-auto border-b border-terminal-border px-3" role="tablist" aria-label="Paper trading activity">{(["positions", "orders", "trades", "performance"] as Tab[]).map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={`border-b-2 px-4 py-3 text-sm capitalize ${tab === item ? "border-terminal-accent text-terminal-text" : "border-transparent text-terminal-muted"}`}>{item}</button>)}</div>
        <div className="overflow-x-auto p-4" role="tabpanel">
          {tab === "positions" ? <table className="w-full min-w-[700px] text-sm"><thead className="text-left text-xs text-terminal-muted"><tr><th className="p-3">Instrument</th><th className="p-3 text-right">Quantity</th><th className="p-3 text-right">Average</th><th className="p-3 text-right">Mark</th><th className="p-3 text-right">Unrealized P&L</th></tr></thead><tbody className="divide-y divide-terminal-border/70">{positions.map((position) => <tr key={position.id}><td className="p-3 font-medium">{position.symbol}</td><td className="p-3 text-right ot-type-data">{position.quantity}</td><td className="p-3 text-right ot-type-data">{money(position.avg_entry_price)}</td><td className="p-3 text-right ot-type-data">{money(position.mark_price)}</td><td className={`p-3 text-right ot-type-data ${position.unrealized_pnl >= 0 ? "text-terminal-pos" : "text-terminal-neg"}`}>{money(position.unrealized_pnl)}</td></tr>)}</tbody></table> : null}
          {tab === "orders" ? <table className="w-full min-w-[620px] text-sm"><thead className="text-left text-xs text-terminal-muted"><tr><th className="p-3">Instrument</th><th className="p-3">Side</th><th className="p-3">Type</th><th className="p-3 text-right">Quantity</th><th className="p-3 text-right">Status</th></tr></thead><tbody className="divide-y divide-terminal-border/70">{orders.map((order) => <tr key={order.id}><td className="p-3 font-medium">{order.symbol}</td><td className="p-3 capitalize">{order.side}</td><td className="p-3 uppercase">{order.order_type}</td><td className="p-3 text-right ot-type-data">{order.quantity}</td><td className="p-3 text-right capitalize text-terminal-muted">{order.status}</td></tr>)}</tbody></table> : null}
          {tab === "trades" ? <table className="w-full min-w-[720px] text-sm"><thead className="text-left text-xs text-terminal-muted"><tr><th className="p-3">Time</th><th className="p-3">Instrument</th><th className="p-3">Side</th><th className="p-3 text-right">Quantity</th><th className="p-3 text-right">Price</th><th className="p-3 text-right">Realized P&L</th></tr></thead><tbody className="divide-y divide-terminal-border/70">{trades.map((trade) => <tr key={trade.id}><td className="p-3 text-terminal-muted">{new Date(trade.timestamp).toLocaleString()}</td><td className="p-3 font-medium">{trade.symbol}</td><td className="p-3 capitalize">{trade.side}</td><td className="p-3 text-right ot-type-data">{trade.quantity}</td><td className="p-3 text-right ot-type-data">{money(trade.price)}</td><td className={`p-3 text-right ot-type-data ${Number(trade.pnl_realized ?? 0) >= 0 ? "text-terminal-pos" : "text-terminal-neg"}`}>{money(trade.pnl_realized)}</td></tr>)}</tbody></table> : null}
          {tab === "performance" ? <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-xs text-terminal-muted">Equity</dt><dd className="mt-2 ot-type-data text-lg">{money(perf?.equity)}</dd></div><div><dt className="text-xs text-terminal-muted">Total return</dt><dd className="mt-2 ot-type-data text-lg">{(Number(perf?.cumulative_return ?? 0) * 100).toFixed(2)}%</dd></div><div><dt className="text-xs text-terminal-muted">Sharpe ratio</dt><dd className="mt-2 ot-type-data text-lg">{Number(perf?.sharpe_ratio ?? 0).toFixed(2)}</dd></div><div><dt className="text-xs text-terminal-muted">Max drawdown</dt><dd className="mt-2 ot-type-data text-lg text-terminal-neg">{(Number(perf?.max_drawdown ?? 0) * 100).toFixed(2)}%</dd></div></dl> : null}
          {((tab === "positions" && !positions.length) || (tab === "orders" && !orders.length) || (tab === "trades" && !trades.length)) ? <p className="py-8 text-center text-sm text-terminal-muted">No {tab} yet.</p> : null}
        </div>
      </section>

      {createOpen ? <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="new-portfolio-title"><div className="w-full max-w-md rounded-lg border border-terminal-border bg-terminal-panel p-5"><div className="flex items-center justify-between"><h2 id="new-portfolio-title" className="text-lg font-semibold">New virtual portfolio</h2><button type="button" onClick={() => setCreateOpen(false)} aria-label="Close dialog"><XMarkIcon className="h-5 w-5" /></button></div><label className="mt-5 block text-xs text-terminal-muted">Name<input aria-label="Portfolio name" className={fieldClass} value={name} onChange={(event) => setName(event.target.value)} /></label><label className="mt-4 block text-xs text-terminal-muted">Initial capital<input aria-label="Initial capital" className={fieldClass} type="number" value={capital} onChange={(event) => setCapital(Number(event.target.value))} /></label><div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => setCreateOpen(false)} className="rounded-md border border-terminal-border px-4 py-2 text-sm text-terminal-muted">Cancel</button><button type="button" onClick={() => void (async () => { try { await createPaperPortfolio({ name, initial_capital: capital }); await loadPortfolios(); setCreateOpen(false); setError(null); } catch (reason) { setError(reason instanceof Error ? reason.message : "Failed to create portfolio"); } })()} className="rounded-md bg-terminal-accent px-4 py-2 text-sm font-semibold text-black">Create portfolio</button></div></div></div> : null}
    </main>
  );
}
