import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Boxes, BrainCircuit, ClipboardList, Loader2, ShieldCheck } from "lucide-react";
import { xppApi } from "./api";
import type { ExperimentSummary } from "./types";

export default function ReproduceList() {
  const [items, setItems] = useState<ExperimentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { xppApi.experiments().then(setItems).catch((e) => setError(String(e.message || e))); }, []);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><ShieldCheck className="text-indigo-600" size={24} />Reproduce</h1>
          <p className="text-sm text-gray-500 mt-1 max-w-3xl">
            Each experiment is a paper broken into its platform, protocol, models and claims. XP Plus checks what the paper leaves out,
            rebuilds it as a digital twin (Danamic transport, or the paper's own model as a black box), compares supported claims, and writes a
            Reproducibility Standard: everything needed to rerun the experiment, with where every value came from.
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4 text-sm text-indigo-900 flex gap-3">
        <ClipboardList size={18} className="mt-0.5 shrink-0" />
        <div>
          <p className="font-medium">How a reproduction runs</p>
          <p className="text-indigo-800/90 mt-0.5">Paper as written → completeness gate (structural · parametric · consistency · model) → tagged resolutions →
            twin → compare → Standard. Physical validation is a separate step outside this public demo. A Standard says "reproduced" only from a judged physical run.</p>
        </div>
      </div>

      {error && <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">XP Plus API unavailable: {error}. Start XP Plus with run_xp_plus.bat.</div>}
      {!items && !error && <div className="text-center py-12 text-gray-400"><Loader2 className="mx-auto animate-spin" /></div>}
      {items && items.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center text-gray-500">No experiments yet. Add an extraction under <code>examples/</code>.</div>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items?.map((e) => (
          <Link key={e.id} to={`/reproduce/${e.id}`} className="bg-white rounded-lg shadow-sm border p-5 hover:shadow-md transition-shadow block">
            <div className="flex items-start justify-between gap-3">
              <div className="bg-indigo-500 p-2.5 rounded-lg text-white shrink-0"><BookOpen size={18} /></div>
              <div className="flex flex-wrap justify-end gap-1">
                {e.models.length > 0 && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-violet-100 text-violet-700"><BrainCircuit size={10} />black-box model</span>}
                {e.has_observations && <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-700">synthetic observations</span>}
              </div>
            </div>
            <h2 className="text-lg font-semibold text-gray-900 mt-3">{e.label}</h2>
            <p className="text-sm text-gray-600 mt-1 line-clamp-2">{e.title}</p>
            <p className="text-xs text-gray-400 mt-1 line-clamp-2">{e.experiment}</p>
            <div className="mt-4 flex items-center gap-4 text-xs text-gray-500">
              <span className="inline-flex items-center gap-1"><Boxes size={12} />{e.n_components} components</span>
              <span>{e.n_claims} claims</span>
              <span>{e.n_resolutions} resolutions</span>
            </div>
            <p className="text-[10px] text-gray-400 font-mono mt-2 truncate">{e.doi ? `doi:${e.doi}` : e.id}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
