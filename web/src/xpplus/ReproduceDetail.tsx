import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CartesianGrid, ComposedChart, ErrorBar, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertTriangle, ArrowLeft, BookOpen, BrainCircuit, CheckCircle2, Download, FileCheck2, Loader2, Play, SearchCheck, ShieldCheck,
} from "lucide-react";
import { xppApi } from "./api";
import RigMap, { taggedFields } from "./RigMap";
import { fmt, label, OVERALL, ProvenanceChip, StatTile, StatusPill, VerdictIcon } from "./ui";
import type { ExperimentDetail, Features, Gap, GateResult, ModelCard, RunOptions, Standard, Tagged } from "./types";

type Tab = "overview" | "rig" | "gaps" | "results" | "twin" | "standard";
const TABS: [Tab, string][] = [["overview", "Overview"], ["rig", "Rig"], ["gaps", "Gaps"], ["results", "Results"], ["twin", "Twin & model"], ["standard", "Standard"]];
const SERIES = ["#2563eb", "#0d9488", "#9333ea", "#ea580c", "#db2777"];
const GAP_SOURCE: Record<string, string> = {
  extraction: "Extraction", gate_structural: "Gate · structural", gate_parametric: "Gate · parametric",
  gate_consistency: "Gate · consistency", gate_model: "Gate · model", comparison: "Comparison",
};

export default function ReproduceDetail() {
  const { experimentId = "" } = useParams();
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [gate, setGate] = useState<GateResult | null>(null);
  const [standard, setStandard] = useState<Standard | null>(null);
  const [busy, setBusy] = useState<"gate" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [options, setOptions] = useState<RunOptions>({ apply_resolutions: true, black_box: true, backend: null, paper_bodenstein: false, reactor_only: false });
  const [search] = useSearchParams();  // demo links: ?run=1 runs XP Plus on load, ?gate=1 checks the paper

  useEffect(() => {
    setDetail(null); setGate(null); setStandard(null); setError(null); setTab((search.get("tab") as Tab) || "overview");
    xppApi.experiment(experimentId).then((d) => {
      setDetail(d);
      setOptions((o) => ({ ...o, apply_resolutions: d.n_resolutions > 0, backend: d.options.backend ?? "botorch" }));
    }).catch((e) => setError(String(e.message || e)));
  }, [experimentId]);

  async function checkGate() {
    setBusy("gate"); setError(null);
    try { setGate(await xppApi.gate(experimentId)); setTab("gaps"); } catch (e) { setError(String((e as Error).message || e)); }
    setBusy(null);
  }
  async function run() {
    setBusy("run"); setError(null);
    const t0 = performance.now();
    try { setStandard(await xppApi.run(experimentId, options)); setElapsed((performance.now() - t0) / 1000); setTab((search.get("tab") as Tab) || "results"); }
    catch (e) { setError(String((e as Error).message || e)); }
    setBusy(null);
  }

  useEffect(() => {
    if (!detail || busy || standard || gate) return;
    if (search.get("run") === "1") run();
    else if (search.get("gate") === "1") checkGate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  const features: Features | undefined = standard?.features ?? detail?.extraction.features;
  const gaps: Gap[] = standard?.gaps ?? (gate ? gate.gaps : detail?.extraction.gaps ?? []);
  const open = gaps.filter((g) => g.status === "open");

  if (error && !detail) return <div className="p-6"><div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div></div>;
  if (!detail || !features) return <div className="text-center py-12 text-gray-400"><Loader2 className="mx-auto animate-spin" /></div>;

  const judged = standard?.results.filter((r) => r.twin_verdict !== "missing_data") ?? [];
  const comp = standard?.results.filter((r) => r.computational !== null && r.computational !== undefined) ?? [];
  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <Link to="/reproduce" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"><ArrowLeft size={14} />All experiments</Link>

      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className="bg-indigo-500 p-2.5 rounded-lg text-white shrink-0"><BookOpen size={20} /></div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold text-gray-900">{detail.label}</h1>
              {standard ? <StatusPill verdict={standard.verdict} /> : gate ? (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${gate.passed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-900"}`}>{gate.passed ? "Gate passed" : "Gate blocked"}</span>
              ) : <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600">Not run</span>}
            </div>
            <p className="text-sm text-gray-700 mt-1">{features.paper.title}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {features.experiment}{features.paper.doi && <> · <a className="text-indigo-700 underline" href={`https://doi.org/${features.paper.doi}`} target="_blank" rel="noreferrer">doi:{features.paper.doi}</a></>}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border">
        <div className="px-5 py-3 border-b flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-800">Reproduction</h2>
          <span className="text-xs text-gray-400">{standard ? `Standard ${standard.standard_id}${elapsed ? ` · ${elapsed.toFixed(1)} s` : ""}` : "XP Plus pipeline"}</span>
        </div>
        <div className="p-5 flex flex-wrap items-center gap-3">
          <button onClick={checkGate} disabled={!!busy} className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">
            {busy === "gate" ? <Loader2 size={16} className="animate-spin" /> : <SearchCheck size={16} />}Check the paper as written
          </button>
          <button onClick={run} disabled={!!busy} className="inline-flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
            {busy === "run" ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}{busy === "run" ? "Running XP Plus…" : "Run XP Plus"}
          </button>
          <div className="flex flex-wrap items-center gap-4 text-xs text-gray-600 ml-2">
            <label className="inline-flex items-center gap-1.5"><input type="checkbox" disabled={!detail.n_resolutions} checked={options.apply_resolutions} onChange={(e) => setOptions({ ...options, apply_resolutions: e.target.checked })} />Apply our resolutions ({detail.n_resolutions})</label>
            {detail.models.length > 0 && <>
              <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={options.black_box} onChange={(e) => setOptions({ ...options, black_box: e.target.checked })} />Black-box twin ({detail.models.join(", ")})</label>
              <label className="inline-flex items-center gap-1.5">Model backend
                <select className="border rounded px-2 py-1 text-xs" value={options.backend ?? "botorch"} onChange={(e) => setOptions({ ...options, backend: e.target.value })}>
                  {["botorch_legacy", "botorch", "sklearn"].map((b) => <option key={b}>{b}</option>)}
                </select></label>
            </>}
            {detail.options.bodenstein && <>
              <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={options.paper_bodenstein} onChange={(e) => setOptions({ ...options, paper_bodenstein: e.target.checked })} />Paper's Bodenstein number ({detail.options.bodenstein})</label>
              <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={options.reactor_only} onChange={(e) => setOptions({ ...options, reactor_only: e.target.checked })} />Reactor-only timing</label>
            </>}
          </div>
        </div>
        {busy === "run" && <p className="px-5 pb-4 -mt-2 text-xs text-gray-500">Gate → {detail.models.length ? "rebuild the paper's model and re-run its validation → black-box twin" : "Danamic twin"} → compare → Standard. In-silico; no hardware is operated.</p>}
        {error && <div role="alert" className="mx-5 mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 whitespace-pre-wrap">{error}</div>}
      </div>

      {standard && <div className="rounded-lg border bg-white px-5 py-3 flex items-center gap-3 text-sm">
        <StatusPill verdict={standard.verdict} /><span className="text-gray-600">{OVERALL[standard.verdict][2]}</span>
      </div>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Gaps closed" value={`${gaps.length - open.length} / ${gaps.length}`} sub={standard ? "in the Standard" : gate ? "paper as written" : "noticed by the extraction"} icon={<FileCheck2 size={18} />} />
        <StatTile label="Blocking gaps open" value={open.filter((g) => g.blocking).length} sub="twin cannot run while any remain" tone={open.some((g) => g.blocking) ? "bg-amber-500" : "bg-emerald-500"} icon={<AlertTriangle size={18} />} />
        <StatTile label="Claims matched by the twin" value={standard ? `${judged.filter((r) => r.twin_verdict === "match").length} / ${judged.length}` : "–"} sub={`${features.claims.length} claims extracted`} tone="bg-blue-500" icon={<CheckCircle2 size={18} />} />
        <StatTile label={comp.length ? "Rebuilt model" : "Physical run"} value={comp.length ? comp.map((r) => fmt(r.computational)).join(" · ") : standard?.physical ? "recorded" : "–"}
          sub={comp.length ? comp.map((r) => r.claim_id).join(" · ") : "Physical validation outside this demo"} tone="bg-violet-500" icon={comp.length ? <BrainCircuit size={18} /> : <ShieldCheck size={18} />} />
      </div>

      <div>
        <div className="flex gap-1 border-b">
          {TABS.map(([key, text]) => (
            <button key={key} onClick={() => setTab(key)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === key ? "border-indigo-600 text-indigo-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
              {text}{key === "gaps" && open.length ? <span className="ml-1.5 text-[10px] bg-amber-100 text-amber-900 rounded-full px-1.5">{open.length}</span> : null}
            </button>
          ))}
        </div>
        <div className="pt-5">
          {tab === "overview" && <Overview features={features} />}
          {tab === "rig" && <RigMap components={features.rig.components} connections={features.rig.connections} gaps={gaps} resolutions={standard ? [] : detail.resolutions} />}
          {tab === "gaps" && <GapsView gaps={gaps} origin={standard ? "Standard" : gate ? "paper as written" : "extraction"} />}
          {tab === "results" && (standard ? <Results standard={standard} /> : <Empty text="Run XP Plus to compare the paper's claims with the twin, the rebuilt model and the physical run." />)}
          {tab === "twin" && (standard ? <TwinModel standard={standard} /> : <ModelCards models={features.models} />)}
          {tab === "standard" && (standard ? <StandardView standard={standard} /> : <Empty text="The Reproducibility Standard is written when XP Plus runs." />)}
        </div>
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed p-10 text-center text-sm text-gray-500">{text}</div>;
}

function Card({ title, count, children }: { title: string; count?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border">
      <div className="px-5 py-3 border-b flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>{count && <span className="text-xs text-gray-400">{count}</span>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Overview({ features }: { features: Features }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Paper">
        <p className="text-sm font-medium text-gray-900">{features.paper.title}</p>
        <p className="text-xs text-gray-500 mt-1">{features.paper.authors.join(", ")}{features.paper.year ? ` · ${features.paper.year}` : ""}</p>
        <p className="text-xs text-gray-500 mt-2"><span className="text-[10px] uppercase tracking-wider text-gray-400 mr-1">Experiment</span>{features.experiment}</p>
      </Card>
      <Card title="Claims" count={`${features.claims.length}`}>
        <table className="w-full text-xs">
          <thead><tr className="text-left text-gray-500 uppercase"><th className="py-1.5 pr-2 font-medium">Claim</th><th className="pr-2 font-medium">Value</th><th className="pr-2 font-medium">Condition</th><th className="font-medium">Tolerance</th></tr></thead>
          <tbody>{features.claims.map((c) => (
            <tr key={c.id} className="border-t"><td className="py-1.5 pr-2"><p className="font-medium text-gray-800">{c.metric.replace(/_/g, " ")}</p><p className="font-mono text-[10px] text-gray-400">{c.id}</p></td>
              <td className="pr-2">{fmt(c.value)} {c.unit}</td>
              <td className="pr-2 text-gray-600">{Object.entries(c.at || {}).map(([k, v]) => `${k} = ${v}`).join(", ") || "–"}</td>
              <td className="text-gray-600">{c.tolerance != null ? `± ${fmt(c.tolerance)}` : "10% / 25%"}</td></tr>))}</tbody>
        </table>
      </Card>
      <Card title="Protocol" count={`${features.protocol.length} steps`}>
        <ol className="space-y-2">{features.protocol.map((s, i) => (
          <li key={s.id} className="rounded-lg border p-3 text-xs">
            <p className="font-medium text-gray-800">Step {i + 1}: {s.description}</p>
            <p className="text-gray-500 mt-0.5"><span className="font-mono">{s.action}</span>{s.component ? ` · ${s.component}` : ""}</p>
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
              {[...Object.entries(s.parameters),
                ...((["wait", "residence_time_ramp"].includes(s.action) || s.duration_s?.value != null) ? [["duration_s", s.duration_s] as [string, Tagged<number>]] : [])]
                .map(([k, t]) => (
                  <span key={k} className="inline-flex items-center gap-1.5">{label(k)}: <b>{t.value === null ? "not reported" : fmt(t.value)}</b><ProvenanceChip provenance={t.provenance} /></span>
                ))}
            </div>
          </li>))}</ol>
      </Card>
      <Card title="Data-driven models" count={`${features.models.length}`}>
        {features.models.length ? <ModelCards models={features.models} compact /> : <p className="text-sm text-gray-500">The paper builds no data-driven model; the twin uses Danamic transport only.</p>}
      </Card>
    </div>
  );
}

function GapsView({ gaps, origin }: { gaps: Gap[]; origin: string }) {
  const [filter, setFilter] = useState<"all" | "open" | "blocking">("all");
  const [source, setSource] = useState("");
  const shown = gaps.filter((g) => (filter === "all" || (filter === "open" ? g.status === "open" : g.blocking && g.status === "open")) && (!source || g.detected_by === source))
    .sort((a, b) => Number(b.status === "open") - Number(a.status === "open") || Number(b.blocking) - Number(a.blocking));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="bg-gray-100 rounded-lg p-0.5 flex text-xs">
          {(["all", "open", "blocking"] as const).map((f) => <button key={f} onClick={() => setFilter(f)} className={`px-3 py-1 rounded-md ${filter === f ? "bg-white shadow text-indigo-600" : "text-gray-600"}`}>{f === "all" ? `All (${gaps.length})` : f === "open" ? "Open" : "Blocking"}</button>)}
        </div>
        <select className="border rounded px-2 py-1 text-xs" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Found by: any</option>{[...new Set(gaps.map((g) => g.detected_by))].map((s) => <option key={s} value={s}>{GAP_SOURCE[s] || s}</option>)}
        </select>
        <span className="text-xs text-gray-400">Source: {origin}. Gaps are unreported values, not zeros.</span>
      </div>
      {shown.map((g) => (
        <article key={g.id} className={`rounded-lg border p-4 ${g.status === "open" && g.blocking ? "border-amber-300 bg-amber-50" : "bg-white"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${g.status === "open" ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-700"}`}>{g.status === "open" ? "Open" : "Resolved"}</span>
            {g.blocking && <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-100 text-red-700">Blocking</span>}
            <span className="text-[10px] uppercase tracking-wider text-gray-500">{GAP_SOURCE[g.detected_by] || g.detected_by}</span>
            <span className="font-mono text-[11px] text-gray-500 break-all">{g.target}</span>
          </div>
          <p className="text-sm text-gray-800 mt-2">{g.description}</p>
          {(g.resolutions || []).map((r) => (
            <div key={r.target} className="mt-2 rounded border bg-white p-2 text-xs flex flex-wrap items-center gap-2">
              <span className="text-gray-500">Closed by</span><span className="font-mono text-[10px]">{r.target.replace(g.target, "") || r.target}</span>
              <b>= {fmt(r.value)}</b><ProvenanceChip provenance={r.provenance} /><span className="text-gray-500">{r.note || r.source}</span>
            </div>))}
          {g.closure_reason && <p className="mt-2 text-xs text-gray-600">Review: {g.closure_reason}</p>}
        </article>
      ))}
      {!shown.length && <Empty text="No gaps match this filter." />}
    </div>
  );
}

function Results({ standard }: { standard: Standard }) {
  const claims = Object.fromEntries(standard.features.claims.map((c) => [c.id, c]));
  const preds = standard.twin?.predictions ?? {};
  const chart = useMemo(() => {
    const pts = standard.results.filter((r) => claims[r.claim_id]?.at && Object.keys(claims[r.claim_id].at!).length === 1 && typeof r.paper === "number");
    if (pts.length < 2) return null;
    const key = Object.keys(claims[pts[0].claim_id].at!)[0];
    const groups = [...new Set(pts.map((r) => r.claim_id.split("_")[0].toUpperCase()))];
    const byX = new Map<number, Record<string, number>>();
    for (const r of pts) {
      const x = claims[r.claim_id].at![key];
      const row = byX.get(x) ?? { x };
      row[`paper_${r.claim_id.split("_")[0].toUpperCase()}`] = r.paper as number;
      if (r.twin != null) { row.twin = r.twin; row.twin_sd = preds[`claim:${r.claim_id}`]?.std ?? 0; }
      byX.set(x, row);
    }
    return { key, groups, metric: pts[0].metric, unit: pts[0].unit, data: [...byX.values()].sort((a, b) => a.x - b.x) };
  }, [standard]);

  return (
    <div className="space-y-4">
      {chart && <Card title={`${chart.metric.replace(/_/g, " ")} along ${chart.key}`} count="paper vs twin (± model SD)">
        <div className="h-72">
          <ResponsiveContainer>
            <ComposedChart data={chart.data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tick={{ fontSize: 11 }} label={{ value: chart.key, position: "insideBottom", offset: -4, fontSize: 11 }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} label={{ value: chart.unit || "", angle: -90, position: "insideLeft", fontSize: 11 }} />
              <Tooltip formatter={(v) => fmt(v as number)} labelFormatter={(x) => `${chart.key} = ${x}`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="twin" name="Twin" stroke="#0d9488" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false}>
                <ErrorBar dataKey="twin_sd" width={4} stroke="#0d9488" />
              </Line>
              {chart.groups.map((g, i) => <Scatter key={g} dataKey={`paper_${g}`} name={`Paper ${g}`} fill={[SERIES[0], SERIES[2], SERIES[3]][i % 3]} shape="square" isAnimationActive={false} />)}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>}
      <div className="bg-white rounded-lg border overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b"><tr>{["Claim", "Paper", "Twin", "", "Physical", "", "Rebuilt model", "", "Tolerance"].map((h, i) => <th key={i} className="py-3 px-4 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>)}</tr></thead>
          <tbody>{standard.results.map((r) => {
            const c = claims[r.claim_id]; const sd = preds[`claim:${r.claim_id}`]?.std;
            return <tr key={r.claim_id} className="border-b last:border-0 hover:bg-gray-50">
              <td className="py-2.5 px-4"><p className="font-medium text-gray-800">{r.metric.replace(/_/g, " ")}{c?.at && Object.keys(c.at).length ? <span className="text-gray-500 font-normal"> · {Object.entries(c.at).map(([k, v]) => `${k} = ${v}`).join(", ")}</span> : null}</p><p className="text-[10px] text-gray-400 font-mono">{r.claim_id}</p></td>
              <td className="px-4 tabular-nums">{fmt(r.paper)} <span className="text-gray-400 text-xs">{r.unit}</span></td>
              <td className="px-4 tabular-nums">{fmt(r.twin)}{sd ? <span className="text-gray-400 text-xs"> ± {fmt(sd)}</span> : null}</td><td className="px-2"><VerdictIcon verdict={r.twin_verdict} /></td>
              <td className="px-4 tabular-nums">{fmt(r.physical)}</td><td className="px-2"><VerdictIcon verdict={r.physical_verdict} /></td>
              <td className="px-4 tabular-nums">{fmt(r.computational)}</td><td className="px-2"><VerdictIcon verdict={r.computational_verdict} /></td>
              <td className="px-4 text-xs text-gray-500" title={c?.tolerance_basis || ""}>{c?.tolerance != null ? `± ${fmt(c.tolerance)}` : "10% / 25%"}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <p className="text-xs text-gray-500">Twin and rebuilt-model columns are model outputs, not measurements. "Reproduced" requires a judged physical run.</p>
    </div>
  );
}

function ModelCards({ models, compact = false }: { models: ModelCard[]; compact?: boolean }) {
  if (!models.length) return <Empty text="No data-driven model in this experiment." />;
  const FIELDS = ["library", "library_version", "kernel", "mean_function", "likelihood", "priors", "output_transform", "hyperparameter_fitting", "training_data", "validation", "metric_definitions", "seeds"];
  return <div className="space-y-4">{models.map((m) => (
    <div key={m.id} className={compact ? "" : "bg-white rounded-lg border p-5"}>
      <p className="text-sm font-semibold text-gray-800 flex items-center gap-2"><BrainCircuit size={15} className="text-violet-600" />{m.id} <span className="text-xs font-normal text-gray-500">{m.family.replace(/_/g, " ")}</span></p>
      {m.purpose && <p className="text-xs text-gray-500 mt-1">{m.purpose}</p>}
      <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2 text-xs">{FIELDS.filter((f) => !compact || ["library", "library_version", "kernel", "validation"].includes(f)).map((f) => {
        const t = m[f] as Tagged | undefined;
        return <div key={f} className="min-w-0"><dt className="text-[10px] uppercase tracking-wider text-gray-500 flex items-center gap-1.5">{label(f)}{t && <ProvenanceChip provenance={t.provenance} />}</dt>
          <dd className="text-gray-800 break-words mt-0.5">{t?.value == null ? <span className="text-amber-800">Not reported</span> : String(t.value)}</dd></div>;
      })}</dl>
      {!compact && <table className="w-full text-xs mt-4">
        <thead><tr className="text-left text-gray-500 uppercase"><th className="py-1.5 font-medium">Input / output</th><th className="font-medium">From the rig</th><th className="font-medium">Normalization</th><th className="font-medium">Definition</th></tr></thead>
        <tbody>{[...m.inputs, ...m.outputs].map((io) => <tr key={io.name} className="border-t">
          <td className="py-1.5 font-mono">{io.name}</td>
          <td>{io.kind ? `${io.kind.replace(/_/g, " ")}${io.node ? ` of ${io.node}` : ""}${io.numerator?.length ? `: ${io.numerator.join("+")} / ${io.denominator?.join("+")}` : ""}` : "model output"}</td>
          <td>[{fmt(io.low?.value)}, {fmt(io.high?.value)}] {io.unit}</td><td className="text-gray-600">{io.definition?.value}</td></tr>)}</tbody>
      </table>}
    </div>))}</div>;
}

function TwinModel({ standard }: { standard: Standard }) {
  return (
    <div className="space-y-4">
      {standard.twin ? <Card title="Digital twin" count={`${standard.twin.fidelity} · ${standard.twin.engine}`}>
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900 mb-3">In-silico execution. This twin does not establish physical readiness or empirical accuracy.</div>
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Modelling assumptions (not from the paper)</p>
        <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700">{standard.twin.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      </Card> : <Empty text="The twin did not run: blocking gaps are open." />}
      {standard.computational.map((c) => <Card key={c.model_id} title={`Rebuilt model · ${c.model_id}`} count={c.backend}>
        <div className="grid gap-3 sm:grid-cols-3">
          {Object.entries(c.metrics).map(([k, q]) => <div key={k} className="rounded-xl bg-slate-50 p-3"><p className="text-[10px] uppercase tracking-wider text-gray-500">{k.replace(/_/g, " ")}</p><p className="text-xl font-bold text-gray-900">{fmt(q.value)}</p></div>)}
          <div className="rounded-xl bg-slate-50 p-3"><p className="text-[10px] uppercase tracking-wider text-gray-500">training rows</p><p className="text-xl font-bold text-gray-900">{c.n_training_points}</p></div>
        </div>
        <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700 mt-3">{c.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        {c.training_data_sha256 && <p className="text-[10px] text-gray-400 font-mono mt-2">training data sha256 {c.training_data_sha256}</p>}
      </Card>)}
      <ModelCards models={standard.features.models} />
    </div>
  );
}

function StandardView({ standard }: { standard: Standard }) {
  const text = useMemo(() => JSON.stringify(standard, null, 2), [standard]);
  const href = useMemo(() => URL.createObjectURL(new Blob([text], { type: "application/json" })), [text]);
  const prov: Record<string, number> = {};
  for (const [, t] of standard.features.rig.components.flatMap((c) => taggedFields(c))) if (t.provenance !== "missing") prov[t.provenance] = (prov[t.provenance] || 0) + 1;
  return (
    <Card title="Reproducibility Standard" count={`v${standard.standard_version}`}>
      <dl className="grid gap-3 sm:grid-cols-3 text-sm">
        <div><dt className="text-[10px] uppercase tracking-wider text-gray-500">Standard</dt><dd className="font-mono text-xs mt-0.5">{standard.standard_id}</dd></div>
        <div><dt className="text-[10px] uppercase tracking-wider text-gray-500">Created</dt><dd className="text-xs mt-0.5">{new Date(standard.created_at).toLocaleString()}</dd></div>
        <div><dt className="text-[10px] uppercase tracking-wider text-gray-500">Verdict</dt><dd className="mt-0.5"><StatusPill verdict={standard.verdict} /></dd></div>
      </dl>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">{Object.entries(prov).map(([p, n]) => <span key={p} className="inline-flex items-center gap-1">{n}<ProvenanceChip provenance={p as never} /></span>)}<span className="text-gray-400">rig values by provenance</span></div>
      <p className="text-xs text-gray-500 mt-3">{standard.iterations.map((i) => i.summary).join(" · ")}</p>
      <a href={href} download={`${standard.standard_id}.json`} className="mt-4 inline-flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700"><Download size={16} />Download Standard (JSON)</a>
      <details className="mt-4"><summary className="cursor-pointer text-xs font-medium">Technical details: full Standard JSON</summary>
        <pre className="mt-2 max-h-96 overflow-auto rounded bg-gray-50 p-3 text-[11px]">{text}</pre></details>
    </Card>
  );
}
