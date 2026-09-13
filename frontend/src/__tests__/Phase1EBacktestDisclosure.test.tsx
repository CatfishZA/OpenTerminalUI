import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ active: vi.fn(), versions: vi.fn(), search: vi.fn() }));
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api/client");
  return { ...actual, fetchActiveDataVersion: api.active, fetchDataVersions: api.versions, searchSymbols: api.search };
});
vi.mock("../components/savedViews/SavedViewsControl", () => ({ SavedViewsControl: () => <button type="button">Saved views</button> }));
vi.mock("../components/backtesting/panels/BacktestingPanels", () => ({
  ChartTabPanel: () => <div>Chart</div>, ComparePanel: () => <div>Compare</div>, DrawdownTerrain3DPanel: () => <div>Terrain</div>,
  DistributionPanel: () => <div>Distribution</div>, DrawdownPanel: () => <div>Drawdown</div>, EquityCurvePanel: () => <div>Equity</div>,
  MonthlyHeatmapPanel: () => <div>Monthly</div>, ParameterSurface3DPanel: () => <div>Surface</div>, RegimeEfficacy3DPanel: () => <div>Regime</div>,
  RollingMetricsPanel: () => <div>Rolling</div>, OrderbookLiquidity3DPanel: () => <div>Orderbook</div>, ImpliedVolatilitySurface3DPanel: () => <div>IV</div>,
  VolatilitySurface3DPanel: () => <div>Volatility</div>, MonteCarloSimulationPanel: () => <div>Monte Carlo</div>, TradesPanel: () => <div>Trades</div>,
}));
vi.mock("../components/backtesting/panels/ParameterSensitivityHeatmap", () => ({ ParameterSensitivityHeatmap: () => <div>Sensitivity</div> }));
vi.mock("../components/backtesting/panels/WalkForwardTimeline", () => ({ WalkForwardTimeline: () => <div>Walk forward</div> }));
vi.mock("../components/backtesting/panels/PerformanceMetricsPanel", () => ({ PerformanceMetricsPanel: () => <div>Metrics</div> }));
vi.mock("../components/backtesting/workspace/MosaicWorkspace", () => ({ MosaicWorkspace: () => <div>Pro workspace</div> }));
vi.mock("../components/backtesting/panels/RobustnessPanel", () => ({ RobustnessPanel: () => <div>Robustness</div> }));
vi.mock("../components/backtesting/panels/SweepPanel", () => ({ SweepPanel: () => <div>Sweep</div> }));

import { BacktestingPage } from "../pages/Backtesting";

describe("Phase 1E Backtest progressive setup", () => {
  beforeEach(() => {
    api.active.mockResolvedValue({ id: "data-v1", name: "Daily snapshot", source: "test", is_active: true });
    api.versions.mockResolvedValue([{ id: "data-v1", name: "Daily snapshot", source: "test", is_active: true }]);
    api.search.mockResolvedValue([]);
  });

  it("defaults to RESEARCH, exposes VERIFIED fields on selection, and keeps advanced settings collapsed", async () => {
    render(<MemoryRouter initialEntries={["/backtesting"]}><BacktestingPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Backtest" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /research/i })[0]).toHaveAttribute("aria-pressed", "true");
    const advanced = screen.getByText("Advanced settings").closest("details");
    expect(advanced).not.toHaveAttribute("open");
    fireEvent.click(screen.getAllByRole("button", { name: /verified/i })[0]);
    expect(await screen.findByLabelText("Verified data version")).toBeVisible();
    expect(screen.getByLabelText("Verified quantity")).toBeVisible();
  });
});
