"""Rig -> Danamic Simulations PlatformDoc + RunDoc.

Only the flow path upstream of the observing detector is simulated. Reservoirs fold into the
pump they feed; valves, BPRs and `other` parts are treated as zero-volume pass-throughs.
Pump flows follow the protocol timeline (constant flow if the protocol sets none).
Every modelling choice not taken from the paper is returned in `assumptions`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..protocol import timeline
from ..schema import Component, PaperFeatures

PASS_THROUGH = ("valve", "back_pressure_regulator", "other")
MIXER_RTD = ("nCSTR", [5.0])
DEFAULT_TEMPERATURE_K = 298.15
# First-order delivery with no dead time, lag or slow mode: the pump delivers what it is told.
IDEAL_PUMP = dict(gain=1.0, beta=0.0, theta=0.0, tau_fast=1e-3, w_slow=0.0)


@dataclass
class TwinOptions:
    rtd_model: str = "plug"            # tubing/reactor RTD when no Bodenstein number is given
    bodenstein: Optional[float] = None  # if set, reactors use ADM with this Bo (assumed/calibrated)
    ideal_unknown_pumps: bool = True    # pumps Danamic has no model for deliver ideally
    connection_holdup: bool = True      # count reported connection tubing as transport delay
    black_box: Optional[str] = None     # model card id: output from the paper's model (fidelity black_box)
    black_box_backend: str = "botorch"


@dataclass
class DanamicInputs:
    platform: object  # fluidsim_twin.schema.PlatformDoc
    run: object       # fluidsim_twin.schema.RunDoc
    cell_id: str
    step_times: dict[str, float] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)


def _ancestors(rig, node: str) -> set[str]:
    seen, stack = set(), [node]
    while stack:
        n = stack.pop()
        if n not in seen:
            seen.add(n)
            stack.extend(rig.upstream(n))
    return seen


def _feed(rig, pump: Component, species: str | None) -> float | None:
    """Concentration of the observed species in the reservoir feeding `pump`, if any."""
    for src in rig.upstream(pump.id):
        res = rig.component(src)
        if res.kind == "reservoir" and species in res.contents and res.contents[species].known:
            return res.contents[species].value
    return None


def adm_param(volume_uL: float, flow_uL_min: float, bodenstein: float) -> float:
    """Danamic ADM grouping a [uL^2/min] for a target Bodenstein number.

    The ADM cell fraction is a Gaussian in swept volume with variance a*tau/2; the dispersion
    model's large-Bo variance is 2 V^2 / Bo. Equating them: a = 4 V^2 / (Bo tau), tau = V/Q.
    """
    tau_min = volume_uL / flow_uL_min
    return 4.0 * volume_uL ** 2 / (bodenstein * tau_min)


def to_danamic(f: PaperFeatures, options: TwinOptions | None = None) -> DanamicInputs:
    from fluidsim_twin.equipment import find_model
    from fluidsim_twin.schema import (
        EdgeDoc, NodeDoc, PlatformDoc, PumpSpec, RtdSpec, RunDoc, ScheduleDoc, TubingSpec,
    )

    opt = options or TwinOptions()
    rig, tl = f.rig, timeline(f)
    measurement = f.measurements[0] if f.measurements else None
    cell_id = measurement.instrument if measurement else rig.of_kind("detector")[0].id
    species = measurement.species if measurement else None
    reactor_rtd = f"ADM with Bo = {opt.bodenstein:g}" if opt.bodenstein else f"'{opt.rtd_model}'"
    assumptions = [f"observation at '{cell_id}'; reactor RTD {reactor_rtd}; other tubing '{opt.rtd_model}'",
                   f"mixers modelled as {MIXER_RTD[0]}({MIXER_RTD[1][0]:g})",
                   "single passive tracer, no kinetics; liquid volumes at the pumps' conditions "
                   "(no thermal expansion in heated sections)"]

    keep = {n for n in _ancestors(rig, cell_id) if rig.component(n).kind != "reservoir"}

    # Contract pass-through parts: a -> valve -> b becomes a -> b.
    edges = [(e.src, e.dst, e) for e in rig.connections if e.src in keep and e.dst in keep]
    for pid in [n for n in keep if rig.component(n).kind in PASS_THROUGH]:
        ins = [x for x in edges if x[1] == pid]
        outs = [x for x in edges if x[0] == pid]
        edges = [x for x in edges if pid not in x[:2]]
        edges += [(a, b, None) for a, _, _ in ins for _, b, _ in outs]
        keep.discard(pid)
        assumptions.append(f"'{pid}' treated as a zero-volume pass-through")

    pumps = [rig.component(n) for n in sorted(keep) if rig.component(n).kind == "pump"]
    schedules = {}
    for p in pumps:
        ts, vs = tl.schedules.get(p.id, ([], []))
        if not ts or ts[0] > 0.0:  # before its first protocol setting a pump runs at its rated flow
            ts, vs = [0.0] + ts, [p.flow_rate_uL_min.value or 0.0] + vs
        schedules[p.id] = ScheduleDoc(t_breaks=ts, values=vs)
    total_flow = sum(s.values[0] for s in schedules.values())

    nodes, total_vol = [], 0.0
    for c in (rig.component(n) for n in sorted(keep)):
        if c.kind == "pump":
            conc = _feed(rig, c, species)
            spec = dict(manufacturer=c.manufacturer.value, model=c.model.value,
                        carries_dye=conc is not None, C_value=conc or 0.0)
            known = c.manufacturer.known and c.model.known and \
                find_model("pump", c.manufacturer.value, c.model.value) is not None
            if not known and opt.ideal_unknown_pumps:
                spec.update(IDEAL_PUMP)
                assumptions.append(f"pump '{c.id}' ({c.manufacturer.value} {c.model.value}): "
                                   "no Danamic model, delivery assumed ideal")
            elif not known:
                assumptions.append(f"pump '{c.id}': Danamic's default pump dynamics (VICI M6)")
            nodes.append(NodeDoc(id=c.id, type="source", pump=PumpSpec(**spec)))
        elif c.kind == "detector":
            nodes.append(NodeDoc(id=c.id, type="sink", kind="cell"))
        elif c.kind in ("mixer", "tubing", "reactor"):
            kw = {}
            if c.inner_diameter_mm.known and c.length_mm.known:
                kw["tubing"] = TubingSpec(material=c.material.value, id_mm=c.inner_diameter_mm.value,
                                          length_mm=c.length_mm.value)
            else:
                kw["V"] = c.volume_uL.value
            if c.kind in ("reactor", "tubing") and c.temperature_C.known:  # incl. heated tubing (preheaters)
                kw["temperature_K"] = c.temperature_C.value + 273.15
            vol = c.volume_estimate_uL() or 0.0
            if c.kind == "mixer":
                rtd = RtdSpec(model=MIXER_RTD[0], params=MIXER_RTD[1])
            elif c.kind == "reactor" and opt.bodenstein:
                rtd = RtdSpec(model="ADM", params=[adm_param(vol, total_flow, opt.bodenstein)])
            else:
                rtd = RtdSpec(model=opt.rtd_model)
            nodes.append(NodeDoc(id=c.id, type="mixer" if c.kind == "mixer" else "reactor", rtd=rtd, **kw))
            total_vol += vol
        else:
            raise ValueError(f"'{c.id}': kind '{c.kind}' upstream of the detector is not supported yet")

    edge_docs = []
    for a, b, conn in edges:
        kw = {}
        if opt.connection_holdup and conn is not None and conn.inner_diameter_mm.known and conn.length_mm.known:
            kw = dict(id_mm=conn.inner_diameter_mm.value, length_mm=conn.length_mm.value,
                      tubing_material=conn.material.value)
            total_vol += math.pi * (conn.inner_diameter_mm.value / 2) ** 2 * conn.length_mm.value
        edge_docs.append(EdgeDoc(src=a, dst=b, **kw))

    tau = total_vol / total_flow * 60.0 if total_flow > 0 else 600.0
    t_end = tl.t_end if tl.t_end > 0 else max(60.0, 3.0 * tau)
    if tl.t_end <= 0:
        assumptions.append("constant flow from t=0 (tracer step at t=0)")
    platform = PlatformDoc(platform_id=(f.experiment or f.paper.title)[:60] or "rig", nodes=nodes, edges=edge_docs)
    fidelity, black_box = "analytical_rtd", None
    if opt.black_box:
        fidelity, black_box = "black_box", _black_box_doc(f, opt)
        assumptions.append(f"output from model '{opt.black_box}' ({opt.black_box_backend}) on the plug-flow "
                           "mean element path; dispersion not propagated through the model")
    run = RunDoc(run_id="twin", platform_ref=platform.platform_id,
                 grid={"t0": 0.0, "t_end": t_end, "dt": t_end / 6000.0},
                 schedules=schedules, temperature_K=DEFAULT_TEMPERATURE_K,
                 fidelity=fidelity, black_box=black_box)
    return DanamicInputs(platform=platform, run=run, cell_id=cell_id,
                         step_times=tl.step_times, assumptions=assumptions)


def _black_box_doc(f: PaperFeatures, opt: TwinOptions):
    from fluidsim_twin.schema import BlackBoxDoc, FeatureDoc
    card = next((m for m in f.models if m.id == opt.black_box), None)
    if card is None:
        raise ValueError(f"no model card '{opt.black_box}' in the extraction")
    feats = [FeatureDoc(name=i.name, kind=i.kind, node=i.node, numerator=i.numerator,
                        denominator=i.denominator, value=i.value.value) for i in card.inputs]
    return BlackBoxDoc(model="xp_plus.blackbox.model:danamic_factory",
                       args={"card_json": card.model_dump_json(), "backend": opt.black_box_backend},
                       features=feats, outputs=[o.name for o in card.outputs])
