import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ create: vi.fn(), portfolios: vi.fn(), positions: vi.fn(), orders: vi.fn(), trades: vi.fn(), performance: vi.fn(), place: vi.fn() }));
vi.mock("../api/client", () => ({
  createPaperPortfolio: api.create, fetchPaperPortfolios: api.portfolios, fetchPaperPositions: api.positions,
  fetchPaperOrders: api.orders, fetchPaperTrades: api.trades, fetchPaperPerformance: api.performance, placePaperOrder: api.place,
}));
vi.mock("../components/trading/HotKeyPanel", () => ({ HotKeyPanel: () => <div>Existing hot-key panel</div> }));

import { ProductPaperTradingPage } from "../pages/ProductPaperTradingPage";

describe("Phase 1E Paper Trading presentation", () => {
  beforeEach(() => {
    api.portfolios.mockResolvedValue([{ id: "paper-1", name: "Core Paper", initial_capital: 100000, current_cash: 90000 }]);
    api.positions.mockResolvedValue([{ id: "p-1", symbol: "NSE:INFY", quantity: 2, avg_entry_price: 1400, mark_price: 1500, unrealized_pnl: 200 }]);
    api.orders.mockResolvedValue([{ id: "o-1", symbol: "NSE:INFY", side: "buy", order_type: "market", quantity: 2, status: "filled" }]);
    api.trades.mockResolvedValue([{ id: "t-1", symbol: "NSE:INFY", side: "buy", quantity: 2, price: 1400, timestamp: "2025-01-01T00:00:00Z", pnl_realized: 0 }]);
    api.performance.mockResolvedValue({ equity: 100200, pnl: 200, cumulative_return: 0.002, sharpe_ratio: 1.1, max_drawdown: -0.01 });
    api.create.mockResolvedValue({ id: "paper-2" });
    api.place.mockResolvedValue({ id: "o-2" });
  });

  it("uses conditional price inputs without changing the order payload", async () => {
    render(<ProductPaperTradingPage />);
    await waitFor(() => expect(api.positions).toHaveBeenCalledWith("paper-1"));
    expect(screen.queryByLabelText("Limit price")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Stop price")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Order type"), { target: { value: "limit" } });
    fireEvent.change(screen.getByLabelText("Limit price"), { target: { value: "1450" } });
    fireEvent.click(screen.getByRole("button", { name: /place buy order/i }));
    await waitFor(() => expect(api.place).toHaveBeenCalledWith(expect.objectContaining({ portfolio_id: "paper-1", order_type: "limit", limit_price: 1450, sl_price: undefined })));
    fireEvent.change(screen.getByLabelText("Order type"), { target: { value: "sl" } });
    expect(screen.getByLabelText("Stop price")).toBeVisible();
    expect(screen.queryByLabelText("Limit price")).not.toBeInTheDocument();
  });

  it("opens the new portfolio dialog and keeps hot keys secondary", async () => {
    render(<ProductPaperTradingPage />);
    expect(screen.queryByText("Existing hot-key panel")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /trading tools/i }));
    expect(screen.getByText("Existing hot-key panel")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /new portfolio/i }));
    expect(screen.getByRole("dialog", { name: "New virtual portfolio" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Create portfolio" }));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith({ name: "Paper Portfolio", initial_capital: 100000 }));
  });

  it("keeps positions, orders, trades, and performance accessible as tabs", async () => {
    render(<ProductPaperTradingPage />);
    await screen.findByText("NSE:INFY");
    for (const label of ["positions", "orders", "trades", "performance"]) expect(screen.getByRole("tab", { name: label })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "orders" }));
    expect(screen.getByText("filled")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "performance" }));
    expect(screen.getByText("Sharpe ratio")).toBeVisible();
  });
});
