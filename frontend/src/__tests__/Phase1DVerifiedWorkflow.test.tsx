import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  orders: vi.fn(), fills: vi.fn(), ledger: vi.fn(), events: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api/client");
  return {
    ...actual,
    fetchSimulationOrders: apiMocks.orders,
    fetchSimulationFills: apiMocks.fills,
    fetchSimulationLedger: apiMocks.ledger,
    fetchSimulationEvents: apiMocks.events,
  };
});

import { ExecutionArtifactsPanel } from "../components/backtesting/ExecutionArtifactsPanel";
import { RunProvenancePanel } from "../components/backtesting/RunProvenancePanel";
import { VerificationModeControl, type VerificationMode } from "../components/backtesting/VerificationModeControl";
import { buildBacktestSubmitPayload, explainVerifiedError } from "../components/backtesting/verifiedWorkflow";

const executionProfile = {
  commission_bps: 1, slippage_model: "fixed_bps", slippage_bps: 2,
  spread_bps: 3, market_impact_bps: 4, volume_cap_pct: 10,
};

function ModeHarness() {
  const [mode, setMode] = useState<VerificationMode>("RESEARCH");
  return <VerificationModeControl value={mode} onChange={setMode} />;
}

describe("Phase 1D VERIFIED workflow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.orders.mockResolvedValue({ run_id: "sim_1", items: [], count: 0 });
    apiMocks.fills.mockResolvedValue({ run_id: "sim_1", items: [], count: 0 });
    apiMocks.ledger.mockResolvedValue({ run_id: "sim_1", items: [], count: 0 });
    apiMocks.events.mockResolvedValue({ run_id: "sim_1", items: [], count: 0 });
  });

  it("defaults to RESEARCH and exposes the accessible VERIFIED selector", () => {
    render(<ModeHarness />);
    const research = screen.getByRole("button", { name: /research/i });
    const verified = screen.getByRole("button", { name: /verified/i });
    expect(research).toHaveAttribute("aria-pressed", "true");
    expect(verified).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(verified);
    expect(verified).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/reproducible daily simulation/i)).toBeVisible();
  });

  it("builds the supported VERIFIED payload without research-only sizing", () => {
    const payload = buildBacktestSubmitPayload({
      mode: "VERIFIED", symbol: "AAPL", market: "NASDAQ", start: "2024-01-01", end: "2024-02-01",
      dataTimeframe: "5m", strategy: "example:sma_crossover", strategyContext: { short_window: 5 },
      tradeCapital: 100000, modelAllocation: 0.75, dataVersionId: "version-2", currency: "USD",
      verifiedQuantity: 7, adjustedSeries: true, executionProfile,
    });
    expect(payload).toMatchObject({
      verification_level: "VERIFIED", data_version_id: "version-2", currency: "USD", timeframe: "1d",
      context: { short_window: 5, quantity: 7 }, config: { initial_cash: 100000, fee_bps: 1, slippage_bps: 2 },
    });
    expect(payload.config).not.toHaveProperty("position_fraction");
    expect(payload.config).not.toHaveProperty("execution_profile");
  });

  it("preserves the existing RESEARCH payload semantics", () => {
    const payload = buildBacktestSubmitPayload({
      mode: "RESEARCH", symbol: "RELIANCE", market: "NSE", start: "", end: "", dataTimeframe: "15m",
      strategy: "example:sma_crossover", strategyContext: {}, tradeCapital: 50000, modelAllocation: 0.6,
      dataVersionId: "", currency: "INR", verifiedQuantity: 1, adjustedSeries: false, executionProfile,
    });
    expect(payload.verification_level).toBe("RESEARCH");
    expect(payload.timeframe).toBe("15m");
    expect(payload.config).toMatchObject({ position_fraction: 0.6, adjusted: false, execution_profile: executionProfile });
    expect(payload.data_version_id).toBeUndefined();
  });

  it("shows VERIFIED provenance and does not invent it for RESEARCH", () => {
    const { rerender } = render(<RunProvenancePanel legacyRunId="bt_123" currency="USD" commissionBps={1} slippageBps={2} result={{
      total_return: 0.1, sharpe: 1, max_drawdown: -0.1, verification_level: "VERIFIED",
      simulation_run_id: "sim_456", data_version_id: "version-2", engine_version: "sim-daily-v1",
      manifest_hash: "manifest0123456789012345", result_hash: "result0123456789012345", daily_bar_path_policy: "WORST_CASE",
    }} />);
    expect(screen.getByText("sim_456")).toBeVisible();
    expect(screen.getByText("version-2")).toBeVisible();
    expect(screen.getByText("sim-daily-v1")).toBeVisible();
    expect(screen.getByText("WORST_CASE")).toBeVisible();
    rerender(<RunProvenancePanel legacyRunId="bt_research" currency="INR" commissionBps={5} slippageBps={3} result={{ total_return: 0.1, sharpe: 1, max_drawdown: -0.1 }} />);
    expect(screen.getByText("Legacy research engine")).toBeVisible();
    expect(screen.queryByText("Simulation Run")).not.toBeInTheDocument();
  });

  it("lazy-loads canonical artifacts by sim ID and orders events by sequence", async () => {
    apiMocks.orders.mockResolvedValue({ run_id: "sim_1", count: 1, items: [{ id: "ord_1", instrument_key: "NASDAQ:EQUITY:AAPL:USD", side: "BUY", order_type: "MARKET", quantity: "5", remaining_quantity: "0", tif: "DAY", status: "FILLED", submitted_at: "2024-01-01T00:00:00Z" }] });
    apiMocks.events.mockResolvedValue({ run_id: "sim_1", count: 2, items: [
      { id: 2, sequence: 20, event_id: "e2", event_type: "ORDER_FILL", event_time: "2024-01-02T00:00:00Z" },
      { id: 1, sequence: 10, event_id: "e1", event_type: "BAR_OPEN", event_time: "2024-01-02T00:00:00Z" },
    ] });
    render(<ExecutionArtifactsPanel simulationRunId="sim_1" />);
    expect(await screen.findByText("ord_1")).toBeVisible();
    expect(apiMocks.orders).toHaveBeenCalledWith("sim_1", { limit: 100 });
    expect(apiMocks.fills).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    await screen.findByText("ORDER_FILL");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("10");
    expect(rows[1]).toHaveTextContent("20");
  });

  it("isolates artifact errors and provides retry", async () => {
    apiMocks.ledger.mockRejectedValueOnce(new Error("Ledger unavailable")).mockResolvedValueOnce({ run_id: "sim_1", items: [], count: 0 });
    render(<ExecutionArtifactsPanel simulationRunId="sim_1" />);
    await screen.findByText(/No orders recorded/i);
    fireEvent.click(screen.getByRole("tab", { name: "Ledger" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ledger unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(apiMocks.ledger).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/No ledger recorded/i)).toBeVisible();
  });

  it("preserves stable VERIFIED error codes", () => {
    expect(explainVerifiedError("VERIFIED_DATA_MISSING: 2024-03-14")).toMatch(/^VERIFIED_DATA_MISSING:/);
  });
});
