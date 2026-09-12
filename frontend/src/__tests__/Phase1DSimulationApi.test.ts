import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api/base", () => ({ api: apiMocks }));

import { fetchBacktestJobResult, fetchBacktestJobStatus, submitBacktestJob } from "../api/backtest";
import { fetchDataVersions } from "../api/ops";
import { fetchSimulationEvents, fetchSimulationFills, fetchSimulationLedger, fetchSimulationManifest, fetchSimulationOrders } from "../api/simulation";

describe("Phase 1D API clients", () => {
  beforeEach(() => {
    apiMocks.get.mockReset().mockResolvedValue({ data: { items: [] } });
    apiMocks.post.mockReset().mockResolvedValue({ data: { run_id: "bt_1", status: "queued" } });
  });

  it.each([
    ["manifest", fetchSimulationManifest], ["orders", fetchSimulationOrders], ["fills", fetchSimulationFills],
    ["ledger", fetchSimulationLedger], ["events", fetchSimulationEvents],
  ])("builds the %s URL with an encoded simulation ID", async (suffix, call) => {
    await call("sim/id", { limit: 100 });
    expect(apiMocks.get.mock.calls[0][0]).toBe(`/v1/simulation/runs/sim%2Fid/${suffix}`);
  });

  it("loads the read-only data-version collection", async () => {
    apiMocks.get.mockResolvedValueOnce({ data: { items: [{ id: "v1", name: "Active", is_active: true }] } });
    await expect(fetchDataVersions()).resolves.toEqual([{ id: "v1", name: "Active", is_active: true }]);
    expect(apiMocks.get).toHaveBeenCalledWith("/data/versions");
  });

  it("uses the canonical compatibility facade for Backtesting jobs", async () => {
    const payload = { symbol: "AAPL", market: "NASDAQ", verification_level: "VERIFIED" as const };
    await submitBacktestJob(payload);
    await fetchBacktestJobStatus("bt/id");
    await fetchBacktestJobResult("bt/id");
    expect(apiMocks.post).toHaveBeenCalledWith("/v1/backtest/submit", payload);
    expect(apiMocks.get).toHaveBeenNthCalledWith(1, "/v1/backtest/status/bt%2Fid");
    expect(apiMocks.get).toHaveBeenNthCalledWith(2, "/v1/backtest/result/bt%2Fid");
  });
});
