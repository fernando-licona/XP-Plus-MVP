// Shapes of the XP Plus contract (xp_plus/schema) as the API serves them. Kept loose on purpose:
// the Python schema is the source of truth.

export type Provenance = "paper_stated" | "inferred" | "measured" | "calibrated" | "assumed" | "missing";
export type Verdict = "match" | "partial" | "miss" | "missing_data";
export type OverallVerdict = "reproduced" | "partially_reproduced" | "not_reproduced" | "insufficient_data";

export interface Tagged<T = unknown> { value: T | null; provenance: Provenance; source?: string | null; note?: string | null }
export type Fields = Record<string, unknown>;

export interface Component extends Fields { id: string; kind: string; name?: string | null }
export interface Connection extends Fields { src: string; dst: string; direct?: boolean }
export interface Claim {
  id: string; metric: string; value: number | string; unit?: string | null; qualifier?: string;
  conditions?: string | null; source?: string | null; at?: Record<string, number>; tolerance?: number | null; tolerance_basis?: string | null;
}
export interface ModelIO { name: string; kind?: string; node?: string | null; numerator?: string[]; denominator?: string[]; unit?: string | null; definition?: Tagged<string>; low?: Tagged<number>; high?: Tagged<number> }
export interface ModelCard extends Fields { id: string; family: string; purpose?: string | null; inputs: ModelIO[]; outputs: ModelIO[] }
export interface Features {
  paper: { title: string; doi?: string | null; authors: string[]; year?: number | null };
  experiment?: string | null;
  rig: { components: Component[]; connections: Connection[] };
  protocol: { id: string; description: string; action: string; component?: string | null; parameters: Record<string, Tagged<number>>; duration_s: Tagged<number> }[];
  measurements: Fields[];
  models: ModelCard[];
  claims: Claim[];
  chemistry: Fields;
  environment: Fields;
}
export interface Resolution { target: string; value: number | string; provenance: Provenance; source?: string | null; note?: string | null }
export interface Gap {
  id: string; target: string; description: string; detected_by: string; blocking: boolean;
  status: "open" | "resolved"; resolutions?: Resolution[]; impact?: string | null; closure_reason?: string | null;
}
export interface Quantity { value: number; unit?: string | null; std?: number | null }
export interface ResultRow {
  claim_id: string; metric: string; unit?: string | null; paper: number | string;
  twin?: number | null; physical?: number | null; computational?: number | null;
  twin_verdict: Verdict; physical_verdict: Verdict; computational_verdict: Verdict;
}
export interface Standard {
  standard_version: string; standard_id: string; created_at: string; verdict: OverallVerdict;
  features: Features; gaps: Gap[]; results: ResultRow[];
  twin?: { engine: string; fidelity: string; assumptions: string[]; predictions: Record<string, Quantity> } | null;
  physical?: { runner: string; run_id?: string | null; observations: Record<string, Quantity>; evidence: Fields[] } | null;
  computational: { model_id: string; backend: string; training_data_sha256?: string | null; n_training_points: number; metrics: Record<string, Quantity>; assumptions: string[] }[];
  iterations: { index: number; changes: string[]; summary: string }[];
}
export interface ExperimentSummary {
  id: string; label: string; title: string; doi?: string | null; year?: number | null; authors: string[]; experiment?: string | null;
  models: string[]; n_claims: number; n_components: number; n_resolutions: number; has_observations: boolean;
  options: { black_box?: string; backend?: string; bodenstein?: number };
}
export interface ExperimentDetail extends ExperimentSummary { extraction: { features: Features; gaps: Gap[] }; resolutions: Resolution[] }
export interface GateResult { passed: boolean; gaps: Gap[] }
export interface RunOptions { apply_resolutions: boolean; black_box: boolean; backend?: string | null; paper_bodenstein: boolean; reactor_only: boolean }

export function isTagged(v: unknown): v is Tagged {
  return !!v && typeof v === "object" && "provenance" in (v as object) && "value" in (v as object);
}
