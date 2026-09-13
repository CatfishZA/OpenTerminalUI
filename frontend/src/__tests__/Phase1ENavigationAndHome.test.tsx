import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  portfolio: vi.fn(), watchlist: vi.fn(), alerts: vi.fn(), presets: vi.fn(), quotes: vi.fn(), news: vi.fn(), dashboard: vi.fn(),
}));

vi.mock("../api/client", () => ({
  fetchPortfolio: api.portfolio,
  fetchWatchlist: api.watchlist,
  fetchAlerts: api.alerts,
  fetchBacktestV1Presets: api.presets,
  fetchQuotesBatch: api.quotes,
  fetchLatestNews: api.news,
}));
vi.mock("../api/intelligence", () => ({ fetchDashboardResults: api.dashboard }));
vi.mock("../components/layout/TerminalShell", () => ({ TerminalShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock("../store/settingsStore", () => ({ useSettingsStore: (selector: (state: { selectedMarket: string }) => unknown) => selector({ selectedMarket: "NSE" }) }));

import { PrimarySidebar } from "../components/layout/PrimarySidebar";
import { ProductHomePage } from "../pages/ProductHomePage";
import { ToolsPage } from "../pages/ToolsPage";

describe("Phase 1E navigation and Home", () => {
  beforeEach(() => {
    localStorage.clear();
    api.portfolio.mockResolvedValue({ items: [{ id: 1, ticker: "RELIANCE" }], summary: { total_cost: 90000, total_value: 100000, overall_pnl: 10000 } });
    api.watchlist.mockResolvedValue([{ id: 1, ticker: "INFY" }]);
    api.alerts.mockResolvedValue([{ id: 1, ticker: "INFY", alert_type: "price", condition: ">", threshold: 1500, status: "active" }]);
    api.presets.mockResolvedValue([{ id: "preset-1" }]);
    api.quotes.mockResolvedValue({ quotes: [{ symbol: "^NSEI", last: 25100, changePct: 0.4 }] });
    api.news.mockResolvedValue([{ id: "news-1", title: "Market event", source: "Desk", url: "https://example.test/news" }]);
    api.dashboard.mockResolvedValue({ modelLab: [{ id: "run-1", name: "Momentum study", status: "complete" }], portfolioLab: [] });
  });

  it("shows the ten labeled first-level destinations and supports active keyboard links", () => {
    render(<MemoryRouter initialEntries={["/backtesting"]}><PrimarySidebar /></MemoryRouter>);
    for (const label of ["Home", "Markets", "Research", "Backtest", "Paper", "Portfolio", "Risk", "Data", "Tools", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeVisible();
    }
    expect(screen.getByRole("link", { name: "Backtest" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText("BT")).not.toBeInTheDocument();
  });

  it("renders the simplified Home hierarchy without the legacy launch composition", async () => {
    render(<MemoryRouter><ProductHomePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    for (const label of ["Portfolio Equity", "Day P&L", "Cash", "Active Alerts"]) expect(screen.getByText(label)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Market focus" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Active work" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Alerts & events" })).toBeVisible();
    expect(screen.queryByText("Launch Matrix")).not.toBeInTheDocument();
    expect(screen.queryByText("AI Market Outlook")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Momentum study")).toBeVisible());
  });

  it("keeps specialist destinations discoverable on Tools", () => {
    render(<MemoryRouter><ToolsPage /></MemoryRouter>);
    for (const label of ["Model Lab", "Portfolio Lab", "Statistical Lab", "Pair Trading", "Saved Views", "Plugins", "Data Quality"]) {
      expect(screen.getByRole("link", { name: label })).toBeVisible();
    }
  });
});
