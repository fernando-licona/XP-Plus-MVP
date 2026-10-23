"""Flow + composition solver for an acyclic flow graph (topological traversal).

Two forward passes in topological order:

* :func:`solve_flows` propagates the volumetric flow ``Q(t)`` on every edge (sources
  emit their delivered flow; mixers/reactors pass the inlet sum; splitters divide by
  ratio).
* :func:`solve_composition` propagates the composition ``C(t)`` on every edge: a mixer
  blends its inlets flow-weighted ``C = sum(Q_i C_i)/sum(Q_i)`` then applies its TV-RTD;
  a reactor applies its RTD to its single inlet; a splitter copies; the cell sink records
  the measured composition.

Each unit's RTD reuses the validated kernels via
:meth:`m6flow.forward.tvrtd.FlowField.from_flow` and the ``signal=`` hook. Only acyclic
graphs are handled (the :class:`~m6flow.network.graph.Flowsheet` topo sort rejects
cycles); recycle is the documented future extension (a time-varying fixed-point /
Volterra problem).
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from ..forward.tvrtd import FlowField, rcell_dispersion, rcell_ncstr, rcell_plug, rcell_poormix
from .graph import (Analyzer, Flowsheet, Mixer, Passthrough, Reactor, Separator, Sink,
                    Source, Splitter, Stream)


def solve_flows(fs: Flowsheet, delivered: dict[str, NDArray], tg: NDArray,
                *, max_iter: int = 100, tol: float = 1e-9) -> dict[Stream, NDArray]:
    """Edge flows ``Q(t)`` [uL/min] by forward propagation.

    ``delivered`` maps each source pump name to its already-delivered flow on ``tg``.
    Acyclic graphs are a single topological pass (byte-identical); cyclic graphs (recycle)
    iterate to a fixed point over the torn feedback edges.
    """
    tears = list(getattr(fs, "_tears", []))
    order = getattr(fs, "_topo", None) or fs.topo_order()
    ef: dict[Stream, NDArray] = {e: np.zeros(len(tg)) for e in tears}
    for _ in range(max_iter if tears else 1):
        prev = {e: ef[e].copy() for e in tears}
        for name in order:
            node = fs.nodes[name]
            outs = fs.out_edges(name)
            if isinstance(node, Source):
                q = np.asarray(delivered[node.pump.name], float)
                for e in outs:
                    ef[e] = q
            elif isinstance(node, (Mixer, Reactor, Analyzer)):
                qin = sum(ef[e] for e in fs.in_edges(name))
                for e in outs:
                    ef[e] = qin
            elif isinstance(node, Splitter):
                qin = sum(ef[e] for e in fs.in_edges(name))
                for e in outs:
                    ef[e] = node.frac_to(e.dst) * qin
            elif isinstance(node, Separator):
                qin = sum(ef[e] for e in fs.in_edges(name))
                for e in outs:
                    ef[e] = node.frac_to(e.dst) * qin       # ideal flow split (like a splitter)
            elif isinstance(node, Passthrough):
                ins = fs.in_edges(name)
                if node.kind == "selector_valve" and node.selected is not None:
                    sel = [e for e in ins if e.src == node.selected]
                    qin = ef[sel[0]] if sel else (ef[ins[0]] if ins else 0.0)
                else:
                    qin = ef[ins[0]] if ins else 0.0        # check valve / first inlet
                for e in outs:
                    ef[e] = qin
            elif isinstance(node, Sink):
                pass
        if tears and max(float(np.max(np.abs(ef[e] - prev[e]))) for e in tears) < tol:
            break
    return ef


def _edge_carry(e, C: NDArray, q: NDArray, tg: NDArray, edge_geom) -> NDArray:
    """Carry a composition across edge ``e``: if the edge has tubing geometry, delay it by the
    tube holdup (plug flow, ``tau = V/Q``) via the validated kernel; else pass through unchanged.

    ``edge_geom`` maps an edge -> :class:`~m6flow.params.Geometry`. When it is None/empty (the
    default) this is the identity, so every existing solve stays byte-identical. ``C`` is either a
    scalar field ``(nt,)`` or a species field ``(ns, nt)``.
    """
    g = edge_geom.get(e) if edge_geom else None
    if g is None:
        return C
    ff = FlowField.from_flow(tg, q, g)
    if np.ndim(C) == 1:
        return rcell_plug(ff, signal=C)
    return np.stack([rcell_plug(ff, signal=C[s]) for s in range(C.shape[0])])


def _apply_rtd(node, ff: FlowField, C_in: NDArray) -> NDArray:
    """Dispatch a node's RTD model on the carried inlet composition ``C_in``."""
    if node.rtd == "plug":
        return rcell_plug(ff, signal=C_in)
    if node.rtd == "nCSTR":
        return rcell_ncstr(ff, node.rtd_params[0], signal=C_in)
    if node.rtd == "ADM":
        return rcell_dispersion(ff, node.rtd_params[0], 0.0, signal=C_in)
    if node.rtd == "laminar":
        return rcell_dispersion(ff, node.rtd_params[0], node.rtd_params[1], signal=C_in)
    raise ValueError(f"unknown RTD model '{node.rtd}' on node {node.name}")


def _inlet_ratio(node, ins, edge_flow, q_tot, eps):
    """Inlet flow ratio ``r(t)=Q_a/Q`` for a poor-mixing mixer, or ``None`` for perfect mixing.

    Defined for a 2+-inlet mixer carrying ``inlet_mix=(n_max,p)``; ``4r(1-r)`` is symmetric so the
    choice of ``ins[0]`` as the reference stream is immaterial. ``None`` keeps the byte-identical
    perfect-mixing path."""
    if getattr(node, "inlet_mix", None) is None or len(ins) < 2:
        return None
    safe = np.where(q_tot > eps, q_tot, 1.0)
    return np.where(q_tot > eps, edge_flow[ins[0]] / safe, 0.0)


def _node_transport(node, ff: FlowField, C_in: NDArray, r: NDArray | None) -> NDArray:
    """Mixer/reactor transport on a 1-D signal: the flow-ratio poor-mixing RTD when ``r`` is given
    (mixer with ``inlet_mix``), else the validated RTD kernel (byte-identical)."""
    im = getattr(node, "inlet_mix", None)
    if im is not None and r is not None:
        return rcell_poormix(ff, im[0], im[1], r, signal=C_in)
    return _apply_rtd(node, ff, C_in)


def solve_composition(fs: Flowsheet, edge_flow: dict[Stream, NDArray], tg: NDArray,
                      *, eps: float = 1e-6, max_iter: int = 100, tol: float = 1e-9,
                      node_ops: dict | None = None, edge_geom: dict | None = None,
                      taps_out: dict | None = None,
                      ) -> tuple[dict[Stream, NDArray], NDArray]:
    """Edge compositions ``C(t)`` + the cell composition, by forward propagation.

    Acyclic graphs are a single topological pass (byte-identical); cyclic graphs iterate
    the torn feedback compositions to a fixed point. ``node_ops`` optionally overrides a
    unit's transport operator: ``node_ops[name](node, ff, C_in, tg) -> C_out`` (used for
    per-node mixed fidelity, e.g. a PDE/CFD engine on one reactor); unmapped nodes (and
    ``node_ops=None``) use the validated analytical RTD kernel (byte-identical).
    """
    tears = list(getattr(fs, "_tears", []))
    order = getattr(fs, "_topo", None) or fs.topo_order()
    ec: dict[Stream, NDArray] = {e: np.zeros(len(tg)) for e in tears}
    cell_C = None
    try:
        cell_name = fs.cell()                # the optical cell: a Sink(cell) or an Analyzer
    except ValueError:
        cell_name = None
    for _ in range(max_iter if tears else 1):
        prev = {e: ec[e].copy() for e in tears}
        for name in order:
            node = fs.nodes[name]
            outs = fs.out_edges(name)
            ins = fs.in_edges(name)
            if isinstance(node, Source):
                c = np.full(len(tg), float(node.pump.C_value))
                for e in outs:
                    ec[e] = _edge_carry(e, c, edge_flow[e], tg, edge_geom)
            elif isinstance(node, (Mixer, Reactor, Analyzer)):
                q_tot = sum(edge_flow[e] for e in ins)
                num = sum(edge_flow[e] * ec[e] for e in ins)
                C_in = np.where(q_tot > eps, num / np.where(q_tot > eps, q_tot, 1.0), 0.0)
                ff = FlowField.from_flow(tg, q_tot, node.geometry(), fin=C_in)
                op = None if node_ops is None else node_ops.get(name)
                if op is not None:
                    C_out = op(node, ff, C_in, tg)
                else:
                    r = _inlet_ratio(node, ins, edge_flow, q_tot, eps)
                    C_out = _node_transport(node, ff, C_in, r)
                if isinstance(node, Analyzer) and node.tap and taps_out is not None:
                    taps_out[name] = C_out               # observable composition at this cell
                if name == cell_name:                    # an inline analyzer serving as the cell
                    cell_C = C_out
                for e in outs:
                    ec[e] = _edge_carry(e, C_out, edge_flow[e], tg, edge_geom)
            elif isinstance(node, (Splitter, Separator)):
                C_in = ec[ins[0]]                    # composition preserved across a split
                for e in outs:
                    ec[e] = _edge_carry(e, C_in, edge_flow[e], tg, edge_geom)
            elif isinstance(node, Passthrough):
                C_in = _passthrough_inlet(node, ins, ec, np.zeros(len(tg)))
                for e in outs:
                    ec[e] = _edge_carry(e, C_in, edge_flow[e], tg, edge_geom)
            elif isinstance(node, Sink):
                if node.kind == "cell":
                    cell_C = ec[ins[0]]
        if tears and max(float(np.max(np.abs(ec[e] - prev[e]))) for e in tears) < tol:
            break
    return ec, cell_C


def _passthrough_inlet(node, ins, ec, zero):
    """The composition a passthrough valve forwards: the selected inlet (selector) or first."""
    if not ins:
        return zero
    if node.kind == "selector_valve" and node.selected is not None:
        sel = [e for e in ins if e.src == node.selected]
        if sel:
            return ec[sel[0]]
    return ec[ins[0]]


def solve_cell_composition(fs: Flowsheet, delivered: dict[str, NDArray],
                           tg: NDArray, *, node_ops: dict | None = None,
                           edge_geom: dict | None = None,
                           taps_out: dict | None = None) -> NDArray:
    """Convenience: flows then composition, returning the cell composition ``C(t)``.

    Pass a mutable ``taps_out`` dict to also collect each :class:`Analyzer` node's observable
    composition (``name -> C(t)``); omit it to keep the byte-identical 1-value return."""
    ef = solve_flows(fs, delivered, tg)
    _, cell = solve_composition(fs, ef, tg, node_ops=node_ops, edge_geom=edge_geom,
                                taps_out=taps_out)
    return cell


# --------------------------------------------------------------- multi-species
def solve_composition_species(fs: Flowsheet, edge_flow: dict[Stream, NDArray], tg: NDArray,
                              species: list[str], source_comp: dict[str, dict], *,
                              eps: float = 1e-6, max_iter: int = 100, tol: float = 1e-9,
                              node_ops: dict | None = None, edge_geom: dict | None = None,
                              taps_out: dict | None = None,
                              ) -> tuple[dict[Stream, NDArray], NDArray]:
    """Edge compositions as a **species vector** ``C(t)`` of shape ``(n_species, n_t)``.

    The multi-species generalisation of :func:`solve_composition`: every edge carries one
    row per species, sources emit their per-species inlet vector (``source_comp[name]`` maps
    species -> inlet concentration; missing species are zero), mixers blend each species
    flow-weighted, and a node's transport is applied **per species** by looping the validated
    scalar kernels (the :class:`FlowField` depends only on flow, so it is built once and
    shared). ``node_ops`` overrides a unit's operator with the *vector* contract
    ``op(node, ff, C_in, tg) -> C_out`` where ``C_in``/``C_out`` are ``(n_species, n_t)`` --
    this is where reaction (a reactive PDE/CFD operator) enters. Returns ``(edge_comp, cell)``
    with ``cell`` the cell-sink species field ``(n_species, n_t)``.

    With a single species sourced from ``{"dye": C_value}`` and ``node_ops=None`` each row
    reduces to the scalar :func:`solve_composition` path value-for-value (the loop calls the
    same kernel with the same ``signal``), so the validated dye model is recovered exactly.
    """
    ns, nt = len(species), len(tg)
    sidx = {s: i for i, s in enumerate(species)}
    tears = list(getattr(fs, "_tears", []))
    order = getattr(fs, "_topo", None) or fs.topo_order()
    ec: dict[Stream, NDArray] = {e: np.zeros((ns, nt)) for e in tears}
    cell_C = None
    try:
        cell_name = fs.cell()                # the optical cell: a Sink(cell) or an Analyzer
    except ValueError:
        cell_name = None
    for _ in range(max_iter if tears else 1):
        prev = {e: ec[e].copy() for e in tears}
        for name in order:
            node = fs.nodes[name]
            outs = fs.out_edges(name)
            ins = fs.in_edges(name)
            if isinstance(node, Source):
                c = np.zeros((ns, nt))
                for s, val in source_comp.get(name, {}).items():
                    if s in sidx:
                        c[sidx[s]] = float(val)
                for e in outs:
                    ec[e] = _edge_carry(e, c, edge_flow[e], tg, edge_geom)
            elif isinstance(node, (Mixer, Reactor, Analyzer)):
                q_tot = sum(edge_flow[e] for e in ins)
                num = sum(edge_flow[e] * ec[e] for e in ins)        # (ns, nt) by broadcast
                safe = np.where(q_tot > eps, q_tot, 1.0)
                C_in = np.where(q_tot > eps, num / safe, 0.0)
                ff = FlowField.from_flow(tg, q_tot, node.geometry())
                op = None if node_ops is None else node_ops.get(name)
                if op is None:
                    r = _inlet_ratio(node, ins, edge_flow, q_tot, eps)
                    C_out = np.stack([_node_transport(node, ff, C_in[s], r) for s in range(ns)])
                else:
                    C_out = np.asarray(op(node, ff, C_in, tg), float).reshape(ns, nt)
                if isinstance(node, Analyzer) and node.tap and taps_out is not None:
                    taps_out[name] = C_out               # observable species field at this cell
                if name == cell_name:                    # an inline analyzer serving as the cell
                    cell_C = C_out
                for e in outs:
                    ec[e] = _edge_carry(e, C_out, edge_flow[e], tg, edge_geom)
            elif isinstance(node, Splitter):
                C_in = ec[ins[0]]                    # composition preserved across a split
                for e in outs:
                    ec[e] = _edge_carry(e, C_in, edge_flow[e], tg, edge_geom)
            elif isinstance(node, Passthrough):
                C_in = _passthrough_inlet(node, ins, ec, np.zeros((ns, nt)))
                for e in outs:
                    ec[e] = _edge_carry(e, C_in, edge_flow[e], tg, edge_geom)
            elif isinstance(node, Separator):
                C_in = ec[ins[0]] if ins else np.zeros((ns, nt))     # inlet species field
                q_in = sum(edge_flow[e] for e in ins) if ins else np.zeros(nt)
                default = node.default_outlet or (outs[0].dst if outs else None)
                for e in outs:
                    routes = node.route(e.dst)
                    frac = np.zeros(ns)
                    for s, f in routes.items():
                        if s in sidx:
                            frac[sidx[s]] = float(f)
                    for s in species:                # unlisted species -> default outlet
                        if s not in routes and e.dst == default:
                            frac[sidx[s]] = 1.0
                    # route species *mass*, then renormalise by this outlet's flow fraction so
                    # the per-outlet field stays a concentration (mass routed / volume routed).
                    q_out = node.frac_to(e.dst) * q_in
                    routed_mass = frac[:, None] * (C_in * q_in)      # (ns, nt)
                    safe = np.where(q_out > eps, q_out, 1.0)
                    routed = np.where(q_out > eps, routed_mass / safe, 0.0)
                    ec[e] = _edge_carry(e, routed, q_out, tg, edge_geom)
            elif isinstance(node, Sink):
                if node.kind == "cell":
                    cell_C = ec[ins[0]]
        if tears and max(float(np.max(np.abs(ec[e] - prev[e]))) for e in tears) < tol:
            break
    return ec, cell_C


def solve_cell_species(fs: Flowsheet, delivered: dict[str, NDArray], tg: NDArray,
                       species: list[str], source_comp: dict[str, dict], *,
                       node_ops: dict | None = None, edge_geom: dict | None = None,
                       taps_out: dict | None = None) -> NDArray:
    """Convenience: flows then multi-species composition, returning the cell field.

    Pass a mutable ``taps_out`` dict to also collect each :class:`Analyzer` node's observable
    species field (``name -> C(t)`` of shape ``(n_species, n_t)``); omit it for the
    byte-identical 1-value return."""
    ef = solve_flows(fs, delivered, tg)
    _, cell = solve_composition_species(fs, ef, tg, species, source_comp,
                                        node_ops=node_ops, edge_geom=edge_geom,
                                        taps_out=taps_out)
    return cell
