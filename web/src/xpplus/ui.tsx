// Small XP Plus presentation pieces in FlowLab's visual language (pills, verdict icons, stat tiles).
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import type { OverallVerdict, Provenance, Verdict } from "./types";

const PROVENANCE: Record<Provenance, [string, string]> = {
  paper_stated: ["Paper stated", "bg-slate-100 text-slate-700"],
  inferred: ["Inferred", "bg-sky-100 text-sky-800"],
  measured: ["Measured", "bg-emerald-100 text-emerald-800"],
  calibrated: ["Calibrated", "bg-teal-100 text-teal-800"],
  assumed: ["Assumed", "bg-purple-100 text-purple-800"],
  missing: ["Missing", "bg-amber-100 text-amber-900"],
};

export function ProvenanceChip({ provenance }: { provenance: Provenance }) {
  const [label, cls] = PROVENANCE[provenance] ?? [provenance, "bg-gray-100 text-gray-700"];
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${cls}`}>{label}</span>;
}

const VERDICT: Record<Verdict, [string, string, typeof CheckCircle2]> = {
  match: ["Match", "text-emerald-700", CheckCircle2],
  partial: ["Partial", "text-amber-700", AlertTriangle],
  miss: ["Miss", "text-red-700", XCircle],
  missing_data: ["No data", "text-gray-400", HelpCircle],
};

export function VerdictIcon({ verdict }: { verdict: Verdict }) {
  const [label, cls, Icon] = VERDICT[verdict];
  return <span className={`inline-flex items-center gap-1 text-xs font-medium ${cls}`} title={label}><Icon size={13} />{label}</span>;
}

export const OVERALL: Record<OverallVerdict, [string, string, string]> = {
  reproduced: ["Reproduced", "bg-emerald-100 text-emerald-700", "Every judged claim matched in the physical run."],
  partially_reproduced: ["Partially reproduced", "bg-amber-100 text-amber-800", "Some claims matched in the physical run; see Results."],
  not_reproduced: ["Not reproduced", "bg-red-100 text-red-700", "The physical run missed the paper's claims."],
  insufficient_data: ["Insufficient data", "bg-gray-100 text-gray-700",
    "No physical run has been judged yet, or blocking gaps are open. Twin and computational results are comparisons, not reproduction."],
};

export function StatusPill({ verdict }: { verdict: OverallVerdict }) {
  const [label, cls] = OVERALL[verdict];
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${cls}`}>{label}</span>;
}

export function StatTile({ label, value, sub, icon, tone = "bg-indigo-500" }: { label: string; value: ReactNode; sub?: ReactNode; icon: ReactNode; tone?: string }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border p-5 flex items-start justify-between">
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
      </div>
      <div className={`${tone} p-2.5 rounded-lg text-white`}>{icon}</div>
    </div>
  );
}

export function fmt(v: unknown): string {
  if (v === null || v === undefined) return "–";
  if (typeof v !== "number") return Array.isArray(v) ? v.join(", ") : String(v);
  const a = Math.abs(v);
  if (a >= 1e4 || (a < 1e-3 && v !== 0)) return v.toExponential(2);
  if (a >= 100) return v.toFixed(1);
  if (a >= 1) return String(+v.toFixed(3));
  return String(+v.toFixed(4));
}

export function label(field: string): string {
  return field.replace(/_uL_min$/, " (µL/min)").replace(/_uL$/, " (µL)").replace(/_mm$/, " (mm)").replace(/_C$/, " (°C)")
    .replace(/_nm$/, " (nm)").replace(/_bar$/, " (bar)").replace(/_M$/, " (M)").replace(/_s$/, " (s)").replace(/_/g, " ").replace(/^[a-z]/, (c) => c.toUpperCase());
}
