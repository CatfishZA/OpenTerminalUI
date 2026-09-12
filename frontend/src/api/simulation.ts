import { api } from "./base";
import type {
  SimulationCollection,
  SimulationEvent,
  SimulationFill,
  SimulationLedgerEntry,
  SimulationManifest,
  SimulationOrder,
  SimulationPortfolioSnapshot,
  SimulationPositionSnapshot,
} from "./types";

export type SimulationResultResponse = {
  run_id: string;
  status: string;
  stage: string;
  result: Record<string, unknown> | null;
  error?: string | null;
};

const runPath = (runId: string): string => `/v1/simulation/runs/${encodeURIComponent(runId)}`;

export async function fetchSimulationResult(runId: string): Promise<SimulationResultResponse> {
  const { data } = await api.get<SimulationResultResponse>(runPath(runId));
  return data;
}

export async function fetchSimulationManifest(runId: string): Promise<SimulationManifest> {
  const { data } = await api.get<SimulationManifest>(`${runPath(runId)}/manifest`);
  return data;
}

async function fetchCollection<T>(runId: string, collection: string, params?: Record<string, unknown>): Promise<SimulationCollection<T>> {
  const { data } = await api.get<SimulationCollection<T>>(`${runPath(runId)}/${collection}`, { params });
  return data;
}

export const fetchSimulationOrders = (runId: string, params?: Record<string, unknown>) =>
  fetchCollection<SimulationOrder>(runId, "orders", params);
export const fetchSimulationFills = (runId: string, params?: Record<string, unknown>) =>
  fetchCollection<SimulationFill>(runId, "fills", params);
export const fetchSimulationLedger = (runId: string, params?: Record<string, unknown>) =>
  fetchCollection<SimulationLedgerEntry>(runId, "ledger", params);
export const fetchSimulationEvents = (runId: string, params?: Record<string, unknown>) =>
  fetchCollection<SimulationEvent>(runId, "events", params);
export const fetchSimulationPortfolio = (runId: string, params?: Record<string, unknown>) =>
  fetchCollection<SimulationPortfolioSnapshot>(runId, "portfolio", params);
export const fetchSimulationPositions = (runId: string, params?: Record<string, unknown>) =>
  fetchCollection<SimulationPositionSnapshot>(runId, "positions", params);
