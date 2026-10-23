"""Resolve a PlatformDoc + RunDoc into an m6flow ``Flowsheet`` and forward-solve inputs.

This is the schema -> m6flow projection (DESIGN.md §7.3): node docs become m6flow node
dataclasses, edges become ``Stream``s, and the run's ZOH schedules are sampled onto the
time grid as the per-pump ``cmds`` arrays. The hardware/edge mapping is byte-for-byte the
same as the m6flow builders, so the analytical engine reproduces them exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
from numpy.typing import NDArray

from m6flow.network.graph import (Analyzer, Flowsheet, Mixer, Passthrough, Reactor,
                                  Separator, Sink, Source, Splitter, Stream)
from m6flow.params import BalanceConst, DEFAULT_BALANCE, Geometry

# Instrument subtypes that SAMPLE a diverted aliquot (destructive) rather than flow through.
# The full sampling subsystem (collection window, robotic transfer) lands later; for now a
# sampled analyzer still records its tap so the topology + observable round-trips.
_SAMPLED_SUBTYPES = {"MS", "HPLC", "UPLC", "LC-MS", "LCMS"}
# Default flow-cell holdup [uL] when an instrument node carries no explicit volume/geometry.
_DEFAULT_CELL_UL = 30.0

from .kinetics import network_from_run
from .registry import geometry_from_tubing, pump_from_spec
from .schema import NodeDoc, PlatformDoc, RunDoc, ScheduleDoc


@dataclass
class ResolvedFlowsheet:
    """Everything the forward solve needs (serves as the engine's SimRequest in Phase 0)."""

    fs: Flowsheet
    t: NDArray                              # time grid [s]
    cmds: dict[str, NDArray]                # pump.name -> commanded flow on t [uL/min]
    A_full: float
    offset: float
    balance: BalanceConst = DEFAULT_BALANCE
    taud_of_Q: bool = False
    species: list[str] = field(default_factory=lambda: ["dye"])
    fidelity: str = "analytical_rtd"
    optical_species: str = "dye"
    network: object = None                  # m6flow-agnostic ReactionNetwork (or None: passive)
    temperature_K: float = 298.15           # run-level isothermal temperature (Arrhenius fallback)
    reactor_temperatures: dict = field(default_factory=dict)  # reactor id -> its own setpoint [K]
    # reactor id -> callable T(grid)->array [K] for a time-VARYING setpoint (ZOH-sampled from the
    # run's temperature_schedule); absent => the constant reactor_temperatures value is used.
    reactor_temperature_profiles: dict = field(default_factory=dict)
    # reactor id -> lumped micromixing factor in (0,1] from the nearest upstream mixer's
    # mixing_efficiency; scales the reactor's reaction extent (segregated reactants react less).
    reactor_mix_factors: dict = field(default_factory=dict)
    # reactor id -> radial diffusion coefficient [mm^2/s] for the 2D-axisymmetric tier (0=segregated).
    reactor_radial_diff: dict = field(default_factory=dict)
    reservoir_depletion: dict = field(default_factory=dict)  # Tier-1 diagnostics (id -> info)
    edge_geom: dict = field(default_factory=dict)  # Tier-2: Stream -> Geometry (tubing holdup delay)
    instrument_specs: dict = field(default_factory=dict)  # instrument id -> readout config (UV-4)
    balance_specs: dict = field(default_factory=dict)     # balance id -> (BalanceConst, b0) gravimetric
    optical_models: object = None          # override per-species optical properties (UV-5); None=>TOML
    black_box: object = None               # BlackBoxDoc for the black_box fidelity (None otherwise)


def _resolve_geometry(node: NodeDoc) -> Geometry | None:
    if node.geometry is not None:
        return Geometry(**node.geometry.model_dump())
    if node.tubing is not None:
        return geometry_from_tubing(node.tubing.id_mm, node.tubing.length_mm,
                                    material=node.tubing.material)
    return None


def _zoh(t: NDArray, sched: ScheduleDoc) -> NDArray:
    """Sample a zero-order-hold schedule onto ``t``: ``values[i]`` holds from ``t_breaks[i]``."""
    tb = np.asarray(sched.t_breaks, float)
    vals = np.asarray(sched.values, float)
    idx = np.clip(np.searchsorted(tb, t, side="right") - 1, 0, len(vals) - 1)
    return vals[idx]


def _build_node(node: NodeDoc):
    if node.type == "source":
        ps = node.pump
        ov = ps.model_dump(exclude={"preset", "name", "manufacturer", "model", "serial",
                                    "nickname"}, exclude_none=True)
        pump = pump_from_spec(ps.preset, ov, name=ps.name or node.id,
                              manufacturer=ps.manufacturer, model=ps.model, serial=ps.serial)
        return Source(name=node.id, pump=pump, cmd_key=node.cmd_key)
    if node.type in ("mixer", "reactor"):
        geom = _resolve_geometry(node)
        V = node.V if node.V is not None else (geom.V_R if geom is not None else None)
        if V is None:
            raise ValueError(f"{node.type} node {node.id!r} has no resolvable volume")
        if node.type == "mixer":
            im = node.inlet_mixing
            inlet_mix = (float(im.n_max), float(im.p)) if im is not None else None
            return Mixer(name=node.id, V=float(V), rtd=node.rtd.model,
                         rtd_params=tuple(node.rtd.params), geom=geom, inlet_mix=inlet_mix)
        return Reactor(name=node.id, V=float(V), rtd=node.rtd.model,
                       rtd_params=tuple(node.rtd.params), geom=geom)
    if node.type == "splitter":
        return Splitter(name=node.id, ratios=tuple((d, float(f)) for d, f in node.ratios))
    if node.type == "instrument":
        # A flow cell: 1-in/1-out RTD pass-through that records its composition as the observable.
        geom = _resolve_geometry(node)
        inst = node.instrument
        if node.V is not None:
            V = node.V
        elif geom is not None:
            V = geom.V_R
        elif inst is not None and inst.manufacturer and inst.model:  # resolve holdup from the cell model
            from .equipment import resolve_flow_cell_config
            V = resolve_flow_cell_config(manufacturer=inst.manufacturer, model=inst.model,
                                         serial=inst.serial)["cell_volume_uL"]
        else:
            V = _DEFAULT_CELL_UL
        rtd_model = node.rtd.model if node.rtd is not None else "plug"
        rtd_params = tuple(node.rtd.params) if node.rtd is not None else ()
        akind = "sampled" if (node.subtype or "").upper() in _SAMPLED_SUBTYPES else "flow_through"
        return Analyzer(name=node.id, V=float(V), rtd=rtd_model, rtd_params=rtd_params,
                        geom=geom, kind=akind, subtype=node.subtype, tap=True)
    if node.type in ("sink", "collection", "balance"):
        kind = {"sink": node.kind or "cell", "collection": "collection",
                "balance": "balance"}[node.type]
        return Sink(name=node.id, kind=kind, subtype=node.subtype)
    if node.type == "check_valve":
        return Passthrough(name=node.id, kind="check_valve")
    if node.type == "selector_valve":
        return Passthrough(name=node.id, kind="selector_valve", selected=node.selected)
    if node.type in ("distillation", "phase_separator"):
        routes = tuple((d, tuple(r.items())) for d, r in (node.species_routes or {}).items())
        return Separator(name=node.id, kind=node.type,
                         flow_ratios=tuple((d, float(f)) for d, f in (node.flow_ratios or [])),
                         species_routes=routes, default_outlet=node.default_outlet)
    raise ValueError(f"unknown node type {node.type!r}")


def _balance_config(node: NodeDoc) -> tuple:
    """Resolve a Balance instrument's gravimetric operator: a per-node ``BalanceConst`` (averaging
    window W_b + settling lag tau_b, defaulting to the validated constants) and the tare baseline b0."""
    inst = node.instrument
    dflt = DEFAULT_BALANCE
    W = inst.settle_window_s if (inst and inst.settle_window_s is not None) else dflt.W_b
    tau = inst.settle_lag_s if (inst and inst.settle_lag_s is not None) else dflt.tau_b
    b0 = inst.tare_g if (inst and inst.tare_g is not None) else 0.0
    return (BalanceConst(W_b=float(W), tau_b=float(tau)), float(b0))


def _instrument_config(node: NodeDoc) -> dict:
    """Resolve an instrument node's readout config (UV-4): optical path length, usable wavelength
    window (spectrometer ∩ light source), resolution + integration time, and the signal kind."""
    from .equipment import model_by_label, resolve_flow_cell_config
    inst = node.instrument
    path = None
    if inst is not None and inst.path_length_mm is not None:
        path = inst.path_length_mm
    elif inst is not None and inst.manufacturer and inst.model:
        path = resolve_flow_cell_config(manufacturer=inst.manufacturer, model=inst.model,
                                        serial=inst.serial)["path_length_mm"]
    signal_kind = (inst.signal_kind if (inst and inst.signal_kind) else None) or "spectrum_vs_time"
    spec = model_by_label(inst.spectrometer, "spectrometer") if inst else None
    lamp = model_by_label(inst.light_source, "light_source") if inst else None
    wl_min, wl_max, res, integ = 200.0, 1100.0, 1.0, 10.0
    if spec is not None:
        wl_min = max(wl_min, float(spec.params.get("wavelength_min_nm", wl_min)))
        wl_max = min(wl_max, float(spec.params.get("wavelength_max_nm", wl_max)))
        res = float(spec.params.get("resolution_nm", res))
        integ = float(spec.params.get("integration_time_ms", integ))
    if lamp is not None:                                 # the lamp clips the usable window further
        wl_min = max(wl_min, float(lamp.params.get("wavelength_min_nm", wl_min)))
        wl_max = min(wl_max, float(lamp.params.get("wavelength_max_nm", wl_max)))
    return {"path_length_mm": float(path if path is not None else 10.0),
            "signal_kind": signal_kind, "observable": "absorbance", "axis_unit": "nm",
            "wl_min": wl_min, "wl_max": wl_max, "resolution_nm": res, "integration_ms": integ}


def _resolve_feeds(platform: PlatformDoc) -> tuple[set, dict, dict]:
    """Collapse reservoir / upstream-selector feeders into the pump they supply.

    A reservoir (optionally via a selector valve) sitting upstream of a *source* pump is a
    feed annotation, not a solvable unit: it sets that pump's inlet composition and is then
    excluded from the flow graph. Returns ``(drop_ids, source_composition, active_feeder)``,
    where ``active_feeder`` maps a source id -> the reservoir id actually feeding it (the one
    the selector chose), used by Tier-1 depletion.
    """
    by_id = {n.id: n for n in platform.nodes}
    upstream: dict[str, list[str]] = {}
    for e in platform.edges:
        upstream.setdefault(e.dst, []).append(e.src)
    drop: set[str] = set()
    src_comp: dict[str, dict] = {}
    active: dict[str, str] = {}
    for s in (n for n in platform.nodes if n.type == "source"):
        for fid in upstream.get(s.id, []):
            fn = by_id.get(fid)
            if fn is None:
                continue
            if fn.type == "reservoir":
                drop.add(fid)
                active[s.id] = fid                       # the feeding reservoir (active line)
                if fn.composition:
                    src_comp[s.id] = dict(fn.composition)
            elif fn.type == "selector_valve":
                drop.add(fid)
                ins = upstream.get(fid, [])
                chosen = fn.selected if fn.selected in ins else (ins[0] if ins else None)
                for rid in ins:                          # drop the reservoirs it selects among
                    if by_id.get(rid) and by_id[rid].type == "reservoir":
                        drop.add(rid)
                if chosen and by_id.get(chosen) and by_id[chosen].type == "reservoir":
                    active[s.id] = chosen
                    if by_id[chosen].composition:
                        src_comp[s.id] = dict(by_id[chosen].composition)
    return drop, src_comp, active


def _cumvol(t: NDArray, Q: NDArray) -> NDArray:
    """Cumulative liquid volume withdrawn [uL] for flow ``Q`` [uL/min] over grid ``t`` [s]."""
    if len(t) < 2:
        return np.zeros_like(t)
    dV = 0.5 * (Q[1:] + Q[:-1]) * np.diff(t) / 60.0      # trapezoid; uL/min * s / 60 -> uL
    return np.concatenate([[0.0], np.cumsum(dV)])


def _apply_depletion(platform: PlatformDoc, nodes: dict, t: NDArray,
                     cmds: dict[str, NDArray], active_feeder: dict) -> dict:
    """Tier-1: drain each finite reservoir against the flow of the pump it feeds, then enforce
    its ``on_empty`` policy on ``cmds`` (mutated in place). Single-phase liquid model, so a dry
    line simply stops delivering liquid; ``stop_run`` additionally halts the whole run at the
    earliest dry-out, ``draw_gas`` stops only that line (gas transport/multiphase is Tier-2).
    Returns per-reservoir diagnostics (t_empty, volume/reagent used, policy)."""
    by_id = {n.id: n for n in platform.nodes}
    records: dict[str, dict] = {}
    stop: list[tuple[float, int]] = []
    for sid, rid in active_feeder.items():
        rn, src = by_id.get(rid), nodes.get(sid)
        if rn is None or rn.reservoir is None or not isinstance(src, Source):
            continue
        rs = rn.reservoir
        if rs.infinite or rs.fidelity != "depletion" or rs.start_volume is None:
            continue
        qkey = src.pump.name
        if qkey not in cmds:
            continue
        cum = _cumvol(t, cmds[qkey])                     # uL withdrawn on the commanded schedule
        idx = int(np.searchsorted(cum, rs.start_volume))
        t_empty = float(t[idx]) if idx < len(t) else None
        used = min(rs.start_volume, float(cum[-1]))
        records[rid] = dict(
            source=sid, pump=qkey, on_empty=rs.on_empty, headspace_gas=rs.headspace_gas,
            start_volume=rs.start_volume, total_draw=float(cum[-1]), volume_used=used,
            t_empty=t_empty, ran_dry=(t_empty is not None),
            reagent_mol={k: c * used * 1e-6 for k, c in (rs.components or {}).items()},
        )
        if t_empty is None:
            continue
        if rs.on_empty == "stop_run":
            stop.append((t_empty, idx))
        else:                                            # draw_gas: this line stops feeding liquid
            cmds[qkey] = cmds[qkey].copy()
            cmds[qkey][idx:] = 0.0
    if stop:                                             # stop_run halts every pump at first dry-out
        t_stop, i_stop = min(stop, key=lambda x: x[0])
        for k in list(cmds):
            cmds[k] = cmds[k].copy()
            cmds[k][i_stop:] = 0.0
        for rec in records.values():
            rec["run_stopped_at"] = t_stop if rec["on_empty"] == "stop_run" else None
    return records


def build_flowsheet(platform: PlatformDoc, run: RunDoc, *,
                    grid_override: NDArray | None = None) -> ResolvedFlowsheet:
    """Project a Platform + Run into an m6flow ``Flowsheet`` plus forward-solve inputs.

    ``grid_override`` replaces the run's grid with an explicit time array (used when fitting
    against a dataset's own timeline).
    """
    drop, feed_comp, active_feeder = _resolve_feeds(platform)
    nodes = {n.id: _build_node(n) for n in platform.nodes if n.id not in drop}
    # reservoir feed composition, then run-level feeds override (run wins).
    for sid, comp in {**feed_comp, **(run.feeds or {})}.items():
        src = nodes.get(sid)
        if isinstance(src, Source):
            nodes[sid] = replace(src, pump=replace(src.pump, composition=dict(comp)))
    edges = [Stream(e.src, e.dst) for e in platform.edges
             if e.src not in drop and e.dst not in drop]
    # Tier-2 transport: edges carrying a tubing run get a holdup Geometry keyed by their Stream,
    # so the species/scalar solver delays composition across them (tau = V/Q). No tubing -> absent.
    edge_geom = {
        Stream(e.src, e.dst): geometry_from_tubing(e.id_mm, e.length_mm, material=e.tubing_material)
        for e in platform.edges
        if e.src not in drop and e.dst not in drop and e.id_mm is not None and e.length_mm is not None
    }
    try:
        fs = Flowsheet(nodes=nodes, edges=edges)
    except ValueError as exc:
        if "cycle" not in str(exc):
            raise
        fs = Flowsheet(nodes=nodes, edges=edges, allow_cycles=True)   # recycle (Phase 5)

    if grid_override is not None:
        t = np.asarray(grid_override, float)
    else:
        g = run.grid
        t = np.arange(g.t0, g.t_end, g.dt)

    # cmds are keyed by pump.name (what the m6flow driver looks up).
    cmds: dict[str, NDArray] = {}
    for n in platform.nodes:
        if n.type != "source":
            continue
        pump = nodes[n.id].pump
        key = n.cmd_key or pump.name
        if key not in run.schedules:
            raise KeyError(f"run has no schedule for source {n.id!r} (key {key!r}); "
                           f"have {sorted(run.schedules)}")
        cmds[pump.name] = _zoh(t, run.schedules[key])

    # Tier-1 reservoir depletion: drain finite feeds, apply on_empty (mutates cmds). Tier-0
    # (infinite/boundary) reservoirs are skipped, so the fast path stays byte-identical.
    depletion = _apply_depletion(platform, nodes, t, cmds, active_feeder)

    instrument_specs = {n.id: _instrument_config(n) for n in platform.nodes
                        if n.type == "instrument" and n.id not in drop}
    balance_specs = {n.id: _balance_config(n) for n in platform.nodes
                     if n.type == "instrument" and (n.subtype or "").upper() == "BALANCE"
                     and n.id not in drop}
    optical = next((s.name for s in run.species if s.is_optical), run.species[0].name)
    # Per-reactor setpoint (heated block). Precedence: run.temperature_schedules -> the node's own
    # setpoint -> the run's temperature. A multi-breakpoint schedule is a time-VARYING profile: its
    # constant fallback (first value) goes in reactor_temperatures and a ZOH callable T(grid) goes in
    # reactor_temperature_profiles for the reactive engine to sample per timestep.
    tsched = run.temperature_schedules or {}
    def _reactor_setpoint(n):
        if n.id in tsched and tsched[n.id].values:
            return float(tsched[n.id].values[0])
        return n.temperature_K if n.temperature_K is not None else run.temperature_K
    reactors = [n for n in platform.nodes if n.type == "reactor" and n.id not in drop]
    reactor_T = {n.id: _reactor_setpoint(n) for n in reactors}
    reactor_Tprof = {n.id: (lambda grid, _s=tsched[n.id]: _zoh(np.asarray(grid, float), _s))
                     for n in reactors if n.id in tsched and len(tsched[n.id].values) > 1}
    # Lumped micromixing factor per reactor = the nearest upstream mixer's mixing_efficiency (BFS
    # upstream); scales the reactor's reaction extent. Absent/1.0 => perfectly mixed (no change).
    by_id = {n.id: n for n in platform.nodes}
    upstream_of: dict = {}
    for e in platform.edges:
        upstream_of.setdefault(e.dst, []).append(e.src)

    def _mix_factor(reactor_id):
        seen, frontier = set(), list(upstream_of.get(reactor_id, []))
        while frontier:
            nid = frontier.pop()
            if nid in seen:
                continue
            seen.add(nid)
            n = by_id.get(nid)
            if n is not None and n.type == "mixer" and n.mixing_efficiency is not None:
                return max(0.0, min(1.0, float(n.mixing_efficiency)))
            frontier.extend(upstream_of.get(nid, []))
        return 1.0
    reactor_mix = {n.id: _mix_factor(n.id) for n in reactors}
    reactor_rdiff = {n.id: float(n.radial_diffusion) for n in reactors
                     if n.radial_diffusion is not None}
    return ResolvedFlowsheet(
        fs=fs, t=t, cmds=cmds,
        A_full=run.observation.A_full, offset=run.observation.offset,
        taud_of_Q=run.taud_of_Q,
        species=[s.name for s in run.species],
        fidelity=run.fidelity,
        optical_species=optical,
        network=network_from_run(run),
        temperature_K=run.temperature_K,
        reactor_temperatures=reactor_T,
        reactor_temperature_profiles=reactor_Tprof,
        reactor_mix_factors=reactor_mix,
        reactor_radial_diff=reactor_rdiff,
        reservoir_depletion=depletion,
        edge_geom=edge_geom,
        instrument_specs=instrument_specs,
        balance_specs=balance_specs,
        black_box=run.black_box,
    )
