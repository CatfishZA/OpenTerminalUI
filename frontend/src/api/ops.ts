import { api } from "./base";
import type {
  KillSwitch,
  DataVersion,
} from "../types";
import type {
  OpsDataQualityReport,
} from "./types";

export type DataVersionInfo = {
  id: string;
  name: string;
  description?: string;
  source?: string;
  is_active: boolean;
  created_at?: string;
  metadata?: Record<string, unknown>;
};

export async function fetchFeedHealth(): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>("/ops/feed-health");
  return data;
}

export async function fetchKillSwitches(): Promise<KillSwitch[]> {
  const { data } = await api.get<{ items: KillSwitch[] }>("/ops/kill-switch");
  return Array.isArray(data?.items) ? data.items : [];
}

export async function setKillSwitch(payload: { scope?: string; enabled: boolean; reason?: string }): Promise<KillSwitch> {
  const { data } = await api.post<KillSwitch>("/ops/kill-switch", payload);
  return data;
}

export async function fetchOpsDataQuality(): Promise<OpsDataQualityReport> {
  const { data } = await api.get<OpsDataQualityReport>("/ops/data-quality");
  return data;
}

export async function fetchActiveDataVersion(): Promise<DataVersion> {
  const { data } = await api.get<DataVersion>("/data/version/active");
  return data;
}

export async function fetchDataVersions(): Promise<DataVersionInfo[]> {
  const { data } = await api.get<{ items?: DataVersionInfo[] }>("/data/versions");
  return Array.isArray(data?.items) ? data.items : [];
}

export async function createDataVersion(payload: {
  name: string;
  description?: string;
  source?: string;
  activate?: boolean;
  metadata?: Record<string, unknown>;
}): Promise<DataVersion> {
  const { data } = await api.post<DataVersion>("/data/version", payload);
  return data;
}
