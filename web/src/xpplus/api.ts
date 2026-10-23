// XP Plus API (xp_plus.app.api), proxied by Vite at /xpp. FlowLab's own API stays at /api.
import type { ExperimentDetail, ExperimentSummary, GateResult, RunOptions, Standard } from "./types";

async function xpp<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/xpp/api${path}`, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw new Error(data.error || `XP Plus API ${res.status}`);
  return data as T;
}

export const xppApi = {
  experiments: () => xpp<ExperimentSummary[]>("/experiments"),
  experiment: (id: string) => xpp<ExperimentDetail>(`/experiments/${encodeURIComponent(id)}`),
  gate: (id: string) => xpp<GateResult>(`/experiments/${encodeURIComponent(id)}/gate`, {}),
  run: (id: string, options: RunOptions) => xpp<Standard>(`/experiments/${encodeURIComponent(id)}/run`, options),
};
