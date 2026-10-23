"""A modular flow-graph (flowsheet) of pump/mixer/reactor/splitter nodes.

The forward model is a directed graph: **nodes** are units and **streams** are directed
edges carrying a time-varying flow ``Q(t)`` and composition ``C(t)``. This module holds
the node/stream types, the :class:`Flowsheet` container with construction invariants, a
topological sort (which rejects cycles), and builders for the validated 2-pump lumped
graph and the 3-pump case study.

Node palette
------------
Source
    A pump: emits a stream of delivered flow + a carried (dye) composition.
Mixer
    N inlets -> 1 outlet: sums inlet flows, blends composition flow-weighted, then
    applies its own TV-RTD (n-CSTR / ADM / laminar / plug).
Reactor
    1 inlet -> 1 outlet: an RTD pass-through (the tubular reactor).
Splitter
    1 inlet -> N outlets: divides flow by ratios; composition is preserved.
Sink
    A measurement node (the UV-VIS cell, or the balance).

Only **acyclic** graphs are solved this round (topological traversal, exact); a cycle
(recycle stream) raises with a pointer to the future fixed-point solver. See
:mod:`m6flow.network.solve` for the flow/composition solver.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from ..params import (Geometry, PumpDelivery, REACTOR_GEOMETRY,
                      PUMP_IN, PUMP_P, PUMP_M50)


# ---------------------------------------------------------------- node types
@dataclass(frozen=True)
class Source:
    """A pump/source node emitting a stream of delivered flow + carried composition."""

    name: str
    pump: PumpDelivery
    cmd_key: str | None = None          # command-schedule key (defaults to pump.name)

    def key(self) -> str:
        return self.cmd_key or self.pump.name


@dataclass(frozen=True)
class Mixer:
    """A mixing node: merge inlets (flow-weighted composition) then apply a TV-RTD."""

    name: str
    V: float                            # mixer volume [uL]
    rtd: str = "nCSTR"                  # "plug" | "nCSTR" | "ADM" | "laminar"
    rtd_params: tuple = ()              # ordered RTD params (nCSTR->(n,); ADM->(a,); ...)
    geom: Geometry | None = None
    inlet_mix: tuple | None = None      # (n_max, p) -> flow-ratio poor-mixing RTD; None = perfect

    def geometry(self) -> Geometry:
        return self.geom or Geometry(V_R=self.V)


@dataclass(frozen=True)
class Reactor:
    """A single-inlet reactor node: an RTD pass-through with its own geometry."""

    name: str
    V: float
    rtd: str = "ADM"
    rtd_params: tuple = ()
    geom: Geometry | None = None

    def geometry(self) -> Geometry:
        return self.geom or Geometry(V_R=self.V)


@dataclass(frozen=True)
class Analyzer:
    """A 1-in/1-out inline measurement cell (UV-Vis / IR / Raman / NMR / RI / ...): an RTD
    pass-through (like a :class:`Reactor`) that ALSO records its composition as an observable
    ``tap``. It is **non-destructive** -- flow + composition continue downstream unchanged save
    for the cell's small holdup/RTD. ``kind="sampled"`` marks a diverted/destructive instrument
    (MS / HPLC), whose collection + characterization are handled by the sampling subsystem."""

    name: str
    V: float = 0.0                       # cell / swept volume [uL]
    rtd: str = "plug"                    # "plug" | "nCSTR" | "ADM" | "laminar"
    rtd_params: tuple = ()
    geom: Geometry | None = None
    kind: str = "flow_through"           # "flow_through" | "sampled"
    subtype: str | None = None           # "UV-Vis" | "FTIR" | "Raman" | "NMR" | "RI" | ...
    tap: bool = True                     # records an observable composition

    def geometry(self) -> Geometry:
        return self.geom or Geometry(V_R=self.V)


@dataclass(frozen=True)
class Splitter:
    """A 1-inlet, N-outlet fork: ``Q_out = frac * Q_in`` per outlet, composition preserved."""

    name: str
    ratios: tuple = ()                  # tuple of (downstream_node_name, fraction)

    def frac_to(self, dst: str) -> float:
        for d, f in self.ratios:
            if d == dst:
                return f
        raise KeyError(f"splitter {self.name} has no outlet to {dst}")


@dataclass(frozen=True)
class Sink:
    """A measurement / terminal node (the optical cell, balance, collection, instrument)."""

    name: str
    kind: str = "cell"                  # "cell" | "balance" | "collection" | "instrument"
    subtype: str | None = None          # e.g. instrument subtype "FTIR" | "HPLC"


@dataclass(frozen=True)
class Passthrough:
    """A 1-in/1-out unit that passes flow + composition unchanged (check valve).

    A check valve enforces flow direction; in the (already-directed, acyclic) forward model
    it is an identity on both flow and composition. A selector valve is the multi-inlet
    variant: it passes exactly the ``selected`` inlet (a stream multiplexer); ``selected``
    is the upstream node name (``None`` -> the first inlet).
    """

    name: str
    kind: str = "check_valve"           # "check_valve" | "selector_valve"
    selected: str | None = None         # selector: upstream node name to pass (None -> first)


@dataclass(frozen=True)
class Separator:
    """An ideal species/phase separator: routes each species to outlets by split fractions.

    ``flow_ratios`` splits the volumetric flow across outlets (like a :class:`Splitter`, so
    the flow pass is unchanged); ``species_routes`` maps ``outlet_node_name -> {species:
    fraction}`` giving the fraction of each species routed to that outlet (unlisted species
    follow ``default_outlet``). A distillation column (separate by volatility) and a phase
    separator (separate by phase) share this ideal-split contract -- a documented idealization,
    not a rigorous VLE/settling model.
    """

    name: str
    kind: str = "distillation"          # "distillation" | "phase_separator"
    flow_ratios: tuple = ()             # ((outlet_name, fraction), ...) -- sums to 1
    species_routes: tuple = ()          # ((outlet_name, ((species, frac), ...)), ...)
    default_outlet: str | None = None   # outlet for species not listed (None -> first outlet)

    def frac_to(self, dst: str) -> float:
        for d, f in self.flow_ratios:
            if d == dst:
                return f
        raise KeyError(f"separator {self.name} has no outlet to {dst}")

    def route(self, dst: str) -> dict:
        for d, r in self.species_routes:
            if d == dst:
                return {s: f for s, f in r}
        return {}


Node = Union[Source, Mixer, Reactor, Analyzer, Splitter, Sink, Passthrough, Separator]


@dataclass(frozen=True)
class Stream:
    """A directed edge from node ``src`` to node ``dst``."""

    src: str
    dst: str


# ---------------------------------------------------------------- flowsheet
@dataclass
class Flowsheet:
    """A directed graph of nodes + streams with construction invariants."""

    nodes: dict                          # name -> Node
    edges: list                          # list[Stream]
    allow_cycles: bool = False           # opt-in recycle (fixed-point solve); default rejects
    _topo: list = field(default_factory=list, repr=False)
    _tears: list = field(default_factory=list, repr=False)   # feedback edges torn to order

    def __post_init__(self):
        for e in self.edges:
            if e.src not in self.nodes or e.dst not in self.nodes:
                raise ValueError(f"edge {e.src}->{e.dst} references an unknown node")
        # split-ratio sanity
        for name, node in self.nodes.items():
            if isinstance(node, Splitter):
                outs = [e.dst for e in self.out_edges(name)]
                rs = {d for d, _ in node.ratios}
                if set(outs) != rs:
                    raise ValueError(f"splitter {name} ratios {rs} != out-edges {set(outs)}")
                if abs(sum(f for _, f in node.ratios) - 1.0) > 1e-9:
                    raise ValueError(f"splitter {name} ratios must sum to 1")
            if isinstance(node, Separator):
                outs = [e.dst for e in self.out_edges(name)]
                rs = {d for d, _ in node.flow_ratios}
                if set(outs) != rs:
                    raise ValueError(f"separator {name} flow_ratios {rs} != out-edges {set(outs)}")
                if abs(sum(f for _, f in node.flow_ratios) - 1.0) > 1e-9:
                    raise ValueError(f"separator {name} flow_ratios must sum to 1")
        try:
            self._topo = self.topo_order()   # acyclic: enforces acyclicity (unchanged)
            self._tears = []
        except ValueError:
            if not self.allow_cycles:
                raise
            self._topo, self._tears = self._pseudo_topo()

    def in_edges(self, name: str) -> list:
        return [e for e in self.edges if e.dst == name]

    def out_edges(self, name: str) -> list:
        return [e for e in self.edges if e.src == name]

    def topo_order(self) -> list:
        """Kahn topological sort of node names; raises on a cycle (recycle)."""
        indeg = {n: 0 for n in self.nodes}
        for e in self.edges:
            indeg[e.dst] += 1
        ready = [n for n, d in indeg.items() if d == 0]
        order = []
        while ready:
            n = ready.pop()
            order.append(n)
            for e in self.out_edges(n):
                indeg[e.dst] -= 1
                if indeg[e.dst] == 0:
                    ready.append(e.dst)
        if len(order) != len(self.nodes):
            raise ValueError(
                "flow graph contains a cycle (recycle stream); recycle is not yet "
                "supported by the solver -- it requires the fixed-point/Volterra "
                "extension flagged in m6flow.network.solve (future work).")
        return order

    def _pseudo_topo(self) -> tuple[list, list]:
        """Order nodes for a cyclic graph, tearing feedback edges (a feedback-arc set).

        Kahn's algorithm; when no zero-in-degree node remains, tear the incoming edges of
        the lowest-in-degree unprocessed node to break the cycle, then continue. Returns
        ``(order, tear_edges)`` where ``tear_edges`` are solved by fixed-point iteration.
        """
        indeg = {n: 0 for n in self.nodes}
        for e in self.edges:
            indeg[e.dst] += 1
        order: list = []
        tears: list = []
        remaining = set(self.nodes)
        while remaining:
            ready = sorted(n for n in remaining if indeg[n] == 0)
            if not ready:
                n = min(sorted(remaining), key=lambda x: indeg[x])   # break a cycle here
                for e in self.in_edges(n):
                    if e.src in remaining:
                        tears.append(e)
                        indeg[n] -= 1
                continue
            for n in ready:
                order.append(n)
                remaining.discard(n)
                for e in self.out_edges(n):
                    if e.dst in remaining:
                        indeg[e.dst] -= 1
        return order, tears

    def sources(self) -> list:
        return [n for n, nd in self.nodes.items() if isinstance(nd, Source)]

    def cell(self) -> str:
        for n, nd in self.nodes.items():
            if isinstance(nd, Sink) and nd.kind == "cell":
                return n
        for n, nd in self.nodes.items():     # fall back to an inline optical analyzer (the cell)
            if isinstance(nd, Analyzer) and nd.tap and nd.kind == "flow_through":
                return n
        raise ValueError("flowsheet has no cell sink")


def _flowsheet(node_list, edge_pairs) -> Flowsheet:
    nodes = {n.name: n for n in node_list}
    edges = [Stream(a, b) for a, b in edge_pairs]
    return Flowsheet(nodes=nodes, edges=edges)


# ---------------------------------------------------------------- builders
def lumped_2pump_flowsheet(rtd: str, rtd_params: tuple,
                           pump_in: PumpDelivery = PUMP_IN,
                           pump_p: PumpDelivery = PUMP_P,
                           V_R: float = 2150.0) -> Flowsheet:
    """The validated 2-pump single-lumped-reactor graph: In+P -> one mixer -> cell.

    Reduces byte-identically to the original ``FlowField`` + ``rcell_*`` path.
    """
    return _flowsheet(
        [Source("In", pump_in), Source("P", pump_p),
         Mixer("lumped", V=V_R, rtd=rtd, rtd_params=rtd_params), Sink("cell")],
        [("In", "lumped"), ("P", "lumped"), ("lumped", "cell")],
    )


# Case-study region volumes [uL]; the model assigned to each region is a *choice*
# (see n_pump_model.tex, "Model granularity and choice"), not fixed by the hardware.
V_MIXER1, V_REACTOR, V_MIXER2 = 203.0, 1677.0, 270.0

# A model spec is a ``(rtd, params)`` pair, e.g. ("nCSTR", (n,)), ("ADM", (a,)),
# ("laminar", (a, b)), or ("plug", ()).
ModelSpec = tuple


def three_pump_flowsheet(mixer1: ModelSpec = ("nCSTR", (10.0,)),
                         reactor: ModelSpec = ("ADM", (2.824e4,)),
                         mixer2: ModelSpec = ("nCSTR", (10.0,)), *,
                         pump_in: PumpDelivery = PUMP_IN,
                         pump_p: PumpDelivery = PUMP_P,
                         pump_m50: PumpDelivery = PUMP_M50) -> Flowsheet:
    """The 3-region rig with a freely-chosen RTD model per module.

    ``In(dye)+P -> mixer1(203) -> reactor(1677) -> mixer2(270)+M50(reference) -> cell``.
    Each module's model is a ``(rtd, params)`` spec, so the reactor may be ``("ADM",(a,))``
    or ``("laminar",(a,b))``, a mixer ``("nCSTR",(n,))`` or ``("plug",())``, etc. --- the
    framework is agnostic to the choice.
    """
    (r1, p1), (rr, pr), (r2, p2) = mixer1, reactor, mixer2
    return _flowsheet(
        [Source("In", pump_in), Source("P", pump_p), Source("M50", pump_m50),
         Mixer("mixer1", V=V_MIXER1, rtd=r1, rtd_params=p1),
         Reactor("reactor", V=V_REACTOR, rtd=rr, rtd_params=pr, geom=REACTOR_GEOMETRY),
         Mixer("mixer2", V=V_MIXER2, rtd=r2, rtd_params=p2),
         Sink("cell")],
        [("In", "mixer1"), ("P", "mixer1"), ("mixer1", "reactor"),
         ("reactor", "mixer2"), ("M50", "mixer2"), ("mixer2", "cell")],
    )


def case_study_3pump_flowsheet(n1: float, a_R: float, n2: float, *,
                               pump_in: PumpDelivery = PUMP_IN,
                               pump_p: PumpDelivery = PUMP_P,
                               pump_m50: PumpDelivery = PUMP_M50) -> Flowsheet:
    """The 3-pump case study with the n-CSTR / ADM / n-CSTR assignment (one example).

    Thin wrapper over :func:`three_pump_flowsheet`; kept for back-compatibility. The
    n-CSTR/ADM/n-CSTR triple is *one illustrative* model choice, not a recommendation.
    """
    return three_pump_flowsheet(("nCSTR", (n1,)), ("ADM", (a_R,)), ("nCSTR", (n2,)),
                                pump_in=pump_in, pump_p=pump_p, pump_m50=pump_m50)


def grouped_3pump_flowsheet(upstream: ModelSpec = ("laminar", (2.824e4, 0.05)),
                            mixer2: ModelSpec = ("nCSTR", (10.0,)), *,
                            pump_in: PumpDelivery = PUMP_IN,
                            pump_p: PumpDelivery = PUMP_P,
                            pump_m50: PumpDelivery = PUMP_M50) -> Flowsheet:
    """The 3-pump rig with the two pre-injection regions *grouped* into one node.

    ``In(dye)+P -> upstream(1880, one model) -> mixer2(270)+M50 -> cell``. The inlet
    micromixer and reactor (203+1677 = 1880 uL) are lumped into a single upstream unit
    --- the grouping a modeller chooses when the data cannot resolve them separately
    (the 2-pump rig grouped all regions into one node; see
    :func:`lumped_2pump_flowsheet`). The reference mixer stays separate because the M50
    injects there.
    """
    (ru, pu), (r2, p2) = upstream, mixer2
    return _flowsheet(
        [Source("In", pump_in), Source("P", pump_p), Source("M50", pump_m50),
         Mixer("upstream", V=V_MIXER1 + V_REACTOR, rtd=ru, rtd_params=pu,
               geom=Geometry(V_R=V_MIXER1 + V_REACTOR)),
         Mixer("mixer2", V=V_MIXER2, rtd=r2, rtd_params=p2),
         Sink("cell")],
        [("In", "upstream"), ("P", "upstream"), ("upstream", "mixer2"),
         ("M50", "mixer2"), ("mixer2", "cell")],
    )
