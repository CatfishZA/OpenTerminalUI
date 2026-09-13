import { useEffect, useMemo, useState } from "react";
import { ArrowRightIcon } from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";

import {
  fetchAlerts,
  fetchBacktestV1Presets,
  fetchLatestNews,
  fetchPortfolio,
  fetchQuotesBatch,
  fetchWatchlist,
  type NewsLatestApiItem,
} from "../api/client";
import { fetchDashboardResults, type DashboardResults } from "../api/intelligence";
import { TerminalShell } from "../components/layout/TerminalShell";
import { useSettingsStore } from "../store/settingsStore";
import type { AlertRule, PortfolioItem, WatchlistItem } from "../types";

const MARKET_SYMBOLS = ["^NSEI", "^BSESN", "^IXIC", "^GSPC", "GC=F"];
const MARKET_LABELS: Record<string, string> = {
  "^NSEI": "Nifty 50",
  "^BSESN": "Sensex",
  "^IXIC": "Nasdaq",
  "^GSPC": "S&P 500",
  "GC=F": "Gold",
};

type HomeData = {
  equity: number | null;
  cost: number;
  pnl: number | null;
  cash: number | null;
  holdings: PortfolioItem[];
  watchlist: WatchlistItem[];
  alerts: AlertRule[];
  presetCount: number;
};

const EMPTY_DATA: HomeData = { equity: null, cost: 0, pnl: null, cash: null, holdings: [], watchlist: [], alerts: [], presetCount: 0 };

function money(value: number | null) {
  return value == null || !Number.isFinite(value)
    ? "—"
    : `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function StatCard({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: "positive" | "negative" | "neutral" }) {
  return (
    <article className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <p className="text-sm text-terminal-muted">{label}</p>
      <p className={`mt-3 ot-type-data text-2xl font-semibold ${tone === "positive" ? "text-terminal-pos" : tone === "negative" ? "text-terminal-neg" : "text-terminal-text"}`}>{value}</p>
      <p className="mt-2 text-xs text-terminal-muted">{detail}</p>
    </article>
  );
}

export function ProductHomePage() {
  const selectedMarket = useSettingsStore((state) => state.selectedMarket);
  const [data, setData] = useState<HomeData>(EMPTY_DATA);
  const [marketRows, setMarketRows] = useState<Array<{ symbol: string; last: number | null; changePct: number | null }>>([]);
  const [news, setNews] = useState<NewsLatestApiItem[]>([]);
  const [results, setResults] = useState<DashboardResults>({ modelLab: [], portfolioLab: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const [portfolio, watchlist, alerts, presets, quotes, headlines, dashboard] = await Promise.allSettled([
        fetchPortfolio(),
        fetchWatchlist(),
        fetchAlerts(),
        fetchBacktestV1Presets(),
        fetchQuotesBatch(MARKET_SYMBOLS, selectedMarket),
        fetchLatestNews(8),
        fetchDashboardResults(4),
      ]);
      if (!active) return;
      const portfolioValue = portfolio.status === "fulfilled" ? portfolio.value : null;
      const equity = portfolioValue?.summary.total_value ?? null;
      const cost = Number(portfolioValue?.summary.total_cost ?? 0);
      setData({
        equity,
        cost,
        pnl: portfolioValue?.summary.overall_pnl ?? (equity == null ? null : equity - cost),
        cash: null,
        holdings: portfolioValue?.items ?? [],
        watchlist: watchlist.status === "fulfilled" ? watchlist.value : [],
        alerts: alerts.status === "fulfilled" ? alerts.value : [],
        presetCount: presets.status === "fulfilled" ? presets.value.length : 0,
      });
      if (quotes.status === "fulfilled") {
        setMarketRows((quotes.value.quotes ?? []).map((quote) => ({ symbol: quote.symbol, last: Number.isFinite(Number(quote.last)) ? Number(quote.last) : null, changePct: Number.isFinite(Number(quote.changePct)) ? Number(quote.changePct) : null })));
      }
      setNews(headlines.status === "fulfilled" ? headlines.value : []);
      setResults(dashboard.status === "fulfilled" ? dashboard.value : { modelLab: [], portfolioLab: [] });
      setLoading(false);
    };
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selectedMarket]);

  const pnlPct = data.pnl == null || data.cost <= 0 ? null : (data.pnl / data.cost) * 100;
  const activeAlerts = useMemo(() => data.alerts.filter((alert) => (alert.status || "active") !== "deleted"), [data.alerts]);
  const activeWork = [...results.modelLab, ...results.portfolioLab].slice(0, 4);

  return (
    <TerminalShell contentClassName="bg-terminal-bg pb-16 md:pb-0" showMobileBottomNav showWorkspaceControls={false}>
      <main className="mx-auto w-full max-w-[1480px] space-y-6 p-4 md:p-6 lg:p-8" aria-labelledby="home-title">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-medium text-terminal-accent">Overview</p>
            <h1 id="home-title" className="mt-1 text-2xl font-semibold text-terminal-text">Welcome back</h1>
            <p className="mt-2 text-sm text-terminal-muted">Your portfolio, markets, and active research in one clear view.</p>
          </div>
          <Link to="/equity/tools" className="inline-flex items-center gap-2 text-sm text-terminal-muted hover:text-terminal-accent">Browse all tools <ArrowRightIcon className="h-4 w-4" /></Link>
        </header>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Portfolio summary">
          <StatCard label="Portfolio Equity" value={loading ? "Loading…" : money(data.equity)} detail={`${data.holdings.length} holdings`} />
          <StatCard label="Day P&L" value="—" detail={data.pnl == null ? "Not provided by the portfolio API" : `Total P&L ${money(data.pnl)} (${pnlPct == null ? "—" : `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`})`} />
          <StatCard label="Cash" value={money(data.cash)} detail="Not provided by the holdings API" />
          <StatCard label="Active Alerts" value={String(activeAlerts.length)} detail={`${data.watchlist.length} watchlist symbols`} />
        </section>

        <section className="rounded-lg border border-terminal-border bg-terminal-panel" aria-labelledby="market-focus-title">
          <div className="flex items-center justify-between border-b border-terminal-border px-5 py-4">
            <div><h2 id="market-focus-title" className="font-semibold text-terminal-text">Market focus</h2><p className="mt-1 text-xs text-terminal-muted">Key indices and instruments</p></div>
            <Link to="/equity/watchlist" className="text-sm text-terminal-muted hover:text-terminal-accent">Open watchlist</Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-sm">
              <thead className="text-xs text-terminal-muted"><tr><th className="px-5 py-3 font-medium">Instrument</th><th className="px-5 py-3 text-right font-medium">Last</th><th className="px-5 py-3 text-right font-medium">Change</th><th className="px-5 py-3 text-right font-medium">Status</th></tr></thead>
              <tbody className="divide-y divide-terminal-border/70">
                {marketRows.length ? marketRows.map((row) => <tr key={row.symbol}><td className="px-5 py-3 font-medium text-terminal-text">{MARKET_LABELS[row.symbol] || row.symbol}</td><td className="px-5 py-3 text-right ot-type-data text-terminal-text">{row.last?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—"}</td><td className={`px-5 py-3 text-right ot-type-data ${(row.changePct ?? 0) >= 0 ? "text-terminal-pos" : "text-terminal-neg"}`}>{row.changePct == null ? "—" : `${row.changePct >= 0 ? "+" : ""}${row.changePct.toFixed(2)}%`}</td><td className="px-5 py-3 text-right text-xs text-terminal-muted">Live</td></tr>) : <tr><td colSpan={4} className="px-5 py-8 text-center text-terminal-muted">{loading ? "Loading markets…" : "Market data unavailable"}</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-2">
          <section className="rounded-lg border border-terminal-border bg-terminal-panel p-5" aria-labelledby="active-work-title">
            <div className="flex items-center justify-between"><h2 id="active-work-title" className="font-semibold text-terminal-text">Active work</h2><Link to="/backtesting" className="text-sm text-terminal-muted hover:text-terminal-accent">Open backtest</Link></div>
            <div className="mt-4 divide-y divide-terminal-border/70">
              {activeWork.length ? activeWork.map((item, index) => <div key={item.id || item.run_id || index} className="flex items-center justify-between gap-4 py-3"><div className="min-w-0"><p className="truncate text-sm font-medium text-terminal-text">{item.name || item.strategy || item.symbol || "Research run"}</p><p className="mt-1 text-xs text-terminal-muted">{item.market || item.status || "Backtest result"}</p></div><span className="shrink-0 text-xs text-terminal-muted">{item.sharpe_ratio ?? item.sharpe ? `Sharpe ${Number(item.sharpe_ratio ?? item.sharpe).toFixed(2)}` : "View result"}</span></div>) : <div className="py-8 text-center text-sm text-terminal-muted">No recent research runs. <Link to="/backtesting" className="text-terminal-accent">Start a backtest</Link></div>}
            </div>
            <p className="mt-3 text-xs text-terminal-muted">{data.presetCount} saved backtest presets available</p>
          </section>

          <section className="rounded-lg border border-terminal-border bg-terminal-panel p-5" aria-labelledby="events-title">
            <div className="flex items-center justify-between"><h2 id="events-title" className="font-semibold text-terminal-text">Alerts & events</h2><Link to="/equity/alerts" className="text-sm text-terminal-muted hover:text-terminal-accent">Manage alerts</Link></div>
            <div className="mt-4 divide-y divide-terminal-border/70">
              {activeAlerts.slice(0, 3).map((alert) => <div key={alert.id} className="py-3"><div className="flex justify-between gap-3"><p className="text-sm font-medium text-terminal-text">{alert.ticker}</p><span className="text-xs text-terminal-accent">Alert</span></div><p className="mt-1 text-xs text-terminal-muted">{alert.condition} {alert.threshold ?? ""}</p></div>)}
              {news.slice(0, Math.max(1, 4 - activeAlerts.length)).map((item) => <a key={String(item.id)} href={item.url} target="_blank" rel="noreferrer" className="block py-3 hover:text-terminal-accent"><p className="line-clamp-1 text-sm font-medium text-terminal-text">{item.title}</p><p className="mt-1 text-xs text-terminal-muted">{item.source}</p></a>)}
              {!activeAlerts.length && !news.length ? <p className="py-8 text-center text-sm text-terminal-muted">No active alerts or recent events.</p> : null}
            </div>
          </section>
        </div>
      </main>
    </TerminalShell>
  );
}
