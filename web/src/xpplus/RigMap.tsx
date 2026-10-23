// Read-only map of a paper's rig (XP Plus extraction), drawn with FlowLab's node/edge language,
// plus a provenance inspector for the selected component or connection.
import { useMemo, useState } from "react";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Archive, Beaker, Box, Droplets, FlaskConical, GitMerge, Minus, ScanLine, ToggleLeft } from "lucide-react";
import { fmt, label, ProvenanceChip } from "./ui";
import { isTagged, type Component, type Connection, type Gap, type Resolution, type Tagged } from "./types";

const KINDS: Record<string, { type: string; label: string; Icon: typeof Box; color: string; surface: string }> = {
  reservoir: { type: "reservoir", label: "Reservoir", Icon: Beaker, color: "text-blue-600", surface: "bg-white" },
  pump: { type: "pump", label: "Pump", Icon: Droplets, color: "text-blue-500", surface: "bg-white" },
  mixer: { type: "mixer", label: "Mixer", Icon: GitMerge, color: "text-indigo-500", surface: "bg-white" },
  tubing: { type: "transfer_line", label: "Tubing", Icon: Minus, color: "text-slate-500", surface: "bg-white" },
  reactor: { type: "reactor", label: "Reactor", Icon: FlaskConical, color: "text-orange-500", surface: "bg-white" },
  detector: { type: "flow_cell", label: "Detector", Icon: ScanLine, color: "text-violet-600", surface: "bg-violet-50" },
  collection: { type: "collector", label: "Collection", Icon: Archive, color: "text-gray-500", surface: "bg-white" },
  valve: { type: "valve", label: "Valve", Icon: ToggleLeft, color: "text-teal-600", surface: "bg-white" },
};
const FALLBACK = { type: "custom", label: "Component", Icon: Box, color: "text-gray-500", surface: "bg-white" };


export function taggedFields(obj: Record<string, unknown>): [string, Tagged][] {
  const out: [string, Tagged][] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (isTagged(v)) out.push([k, v]);
    else if (v && typeof v === "object" && !Array.isArray(v)) {
      for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) if (isTagged(v2)) out.push([`${k}.${k2}`, v2]);
    }
  }
  return out;
}

function RigNode({ data, selected }: NodeProps) {
  const d = data as { component: Component; openGaps: number; blocking: number; known: number; missing: number };
  const meta = KINDS[d.component.kind] || FALLBACK;
  return (
    <div className={`rounded-2xl shadow-sm border-2 w-[180px] ${meta.surface} ${selected ? "border-blue-500 shadow-lg ring-4 ring-blue-100" : d.blocking ? "border-amber-400" : "border-gray-200"}`}>
      <Handle type="target" position={Position.Left} style={{ width: 10, height: 10, background: "#3b82f6", border: "2px solid white" }} />
      <div className="flex items-center gap-1.5 px-3 pt-2.5">
        <meta.Icon size={13} className={meta.color} />
        <span className="text-xs font-semibold text-gray-800 truncate" title={d.component.name || d.component.id}>{d.component.name || d.component.id}</span>
      </div>
      <div className="h-24 mx-3 my-2 rounded-lg bg-gradient-to-b from-white/20 to-slate-50/70 flex items-center justify-center">
        <meta.Icon size={46} strokeWidth={1.2} className="text-gray-300" />
      </div>
      <div className="flex items-center justify-between px-3 pb-2.5 gap-1">
        <span className="text-[10px] uppercase tracking-wider text-gray-500">{meta.label}</span>
        {d.openGaps ? (
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${d.blocking ? "bg-amber-100 text-amber-900" : "bg-gray-100 text-gray-600"}`}>
            {d.openGaps} gap{d.openGaps === 1 ? "" : "s"}
          </span>
        ) : <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-700">complete</span>}
      </div>
      <Handle type="source" position={Position.Right} style={{ width: 10, height: 10, background: "#3b82f6", border: "2px solid white" }} />
    </div>
  );
}
const nodeTypes = { rig: RigNode };

function layers(components: Component[], connections: Connection[]): Record<string, number> {
  const depth: Record<string, number> = Object.fromEntries(components.map((c) => [c.id, 0]));
  for (let pass = 0; pass < components.length; pass++)
    for (const e of connections) if (depth[e.src] !== undefined && depth[e.dst] !== undefined) depth[e.dst] = Math.max(depth[e.dst], depth[e.src] + 1);
  return depth;
}

function tubingLabel(e: Connection): { text: string; reported: boolean } {
  if (e.direct) return { text: "direct", reported: true };
  const id = (e.inner_diameter_mm as Tagged)?.value, len = (e.length_mm as Tagged)?.value;
  if (id == null && len == null) return { text: "tubing not reported", reported: false };
  return { text: [id != null ? `ID ${fmt(id)} mm` : "ID ?", len != null ? `${fmt(len)} mm` : "length ?"].join(" · "), reported: id != null && len != null };
}

export default function RigMap({ components, connections, gaps, resolutions = [] }: {
  components: Component[]; connections: Connection[]; gaps: Gap[]; resolutions?: Resolution[];
}) {
  const [selected, setSelected] = useState<{ type: "component" | "connection"; id: string } | null>(null);
  const graph = useMemo(() => {
    const depth = layers(components, connections);
    const perLayer: Record<number, number> = {};
    const nodes: Node[] = components.map((c) => {
      const layer = depth[c.id] ?? 0, row = (perLayer[layer] = (perLayer[layer] ?? -1) + 1);
      const mine = gaps.filter((g) => g.status === "open" && g.target.startsWith(`rig.components.${c.id}`));
      return { id: c.id, type: "rig", position: { x: layer * 225, y: row * 200 }, data: {
        component: c, openGaps: mine.length, blocking: mine.filter((g) => g.blocking).length } };
    });
    const edges: Edge[] = connections.map((e) => {
      const t = tubingLabel(e);
      return { id: `${e.src}->${e.dst}`, source: e.src, target: e.dst, animated: true, label: t.text,
        style: { stroke: "#3b82f6", strokeWidth: 2.5 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6" },
        labelStyle: { fontSize: 10, fill: t.reported ? "#374151" : "#92400e" },
        labelBgStyle: { fill: t.reported ? "rgba(255,255,255,.9)" : "#fef3c7" }, labelBgPadding: [6, 3] as [number, number], labelBgBorderRadius: 4 };
    });
    return { nodes, edges };
  }, [components, connections, gaps]);

  const target = selected ? `rig.${selected.type === "component" ? "components" : "connections"}.${selected.id}` : "";
  const object = selected?.type === "component" ? components.find((c) => c.id === selected.id)
    : selected ? connections.find((e) => `${e.src}->${e.dst}` === selected.id) : undefined;
  const related = gaps.filter((g) => target && (g.target === target || g.target.startsWith(target + ".")));
  const resolvedHere = resolutions.filter((r) => target && r.target.startsWith(target + "."));

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="h-[620px] overflow-hidden rounded-lg border bg-gray-50">
        <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.04 }} minZoom={0.15} maxZoom={1.6}
          nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }}
          onNodeClick={(_, n) => setSelected({ type: "component", id: n.id })}
          onEdgeClick={(_, e) => setSelected({ type: "connection", id: e.id })} onPaneClick={() => setSelected(null)}>
          <Background gap={20} color="#d1d5db" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <aside className="rounded-lg border bg-white overflow-hidden">
        <div className="bg-slate-50 p-3 border-b">
          <p className="text-[10px] uppercase tracking-wider text-gray-500">Provenance inspector</p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5 break-words">
            {object ? String((object as Component).name || selected?.id) : "Select a component or connection"}
          </p>
          {target && <p className="text-[10px] font-mono text-gray-400 mt-0.5 break-all">{target}</p>}
        </div>
        <div className="p-3 space-y-3 max-h-[560px] overflow-y-auto">
          {!object && <p className="text-xs text-gray-500">Every value in the rig carries where it came from: stated in the paper, inferred, measured on our build, or assumed. Missing values are gaps, not zeros.</p>}
          {object && taggedFields(object).filter(([k, t]) => t.value !== null || related.some((g) => g.target.endsWith(`.${k}`))).map(([k, t]) => (
            <div key={k} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-gray-600">{label(k)}</span>
                <ProvenanceChip provenance={t.provenance} />
              </div>
              <p className="text-sm text-gray-900 mt-0.5">{t.value === null ? <span className="text-amber-800">Not reported</span> : fmt(t.value)}</p>
              {(t.source || t.note) && <p className="text-gray-500 mt-0.5 break-words">{t.source || t.note}</p>}
            </div>
          ))}
          {object && !taggedFields(object).some(([, t]) => t.value !== null) && <p className="text-xs text-amber-900">Nothing about this {selected?.type} is reported in the paper.</p>}
          {related.length > 0 && <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Gaps here</p>
            <ul className="space-y-1.5">{related.map((g) => (
              <li key={g.id} className={`rounded border p-2 text-xs ${g.status === "open" && g.blocking ? "border-amber-300 bg-amber-50" : "bg-white"}`}>
                <span className="font-mono text-[10px] text-gray-500">{g.target.replace(target, "") || "(whole)"}</span>
                <p className="text-gray-700">{g.description}</p>
                <p className="mt-0.5 text-[10px] text-gray-500">{g.status}{g.blocking ? " · blocking" : ""}</p>
              </li>))}</ul>
          </div>}
          {resolvedHere.length > 0 && <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Our resolutions</p>
            <ul className="space-y-1.5">{resolvedHere.map((r) => (
              <li key={r.target} className="rounded border bg-white p-2 text-xs">
                <div className="flex items-center justify-between"><span className="font-medium">{label(r.target.split(".").pop() || "")} = {fmt(r.value)}</span><ProvenanceChip provenance={r.provenance} /></div>
                {(r.note || r.source) && <p className="text-gray-500 mt-0.5">{r.note || r.source}</p>}
              </li>))}</ul>
          </div>}
        </div>
      </aside>
    </div>
  );
}
