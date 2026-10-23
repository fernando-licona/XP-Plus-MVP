"""PlatformDoc — the reusable *rig hardware* (DESIGN.md §7.1).

Topology (nodes + directed edges) plus per-node hardware attributes: sub-type, geometry or
tubing, RTD assignment, and default operating set-points. No flow commands, no species —
those live in a RunDoc. A resolved Platform+Run projects to an m6flow ``Flowsheet``
(see :mod:`fluidsim_twin.build`).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

NodeType = Literal[
    "source", "mixer", "reactor", "splitter", "sink",
    # Phase C equipment palette
    "reservoir",        # upstream feed tank (collapses into the pump it feeds)
    "selector_valve",   # alternate streams to a pump / mux a junction
    "check_valve",      # one-way passthrough (backflow guard)
    "collection",       # terminal collection container
    "distillation",     # separate by species (ideal split)
    "phase_separator",  # separate by phase (ideal split)
    "balance",          # gravimetric measurement (combinable with collection)
    "instrument",       # characterization instrument (FTIR / HPLC / ...)
]


class _Doc(BaseModel):
    """Base: forbid unknown keys so typos in authored TOML are caught."""

    model_config = ConfigDict(extra="forbid")


class PumpSpec(_Doc):
    """How a pump is specified. Preferred: pick a ``manufacturer`` + ``model`` (idealized from
    the equipment library) and optionally a calibrated unit by ``serial``. ``preset`` is the
    legacy registry key (kept for back-compat); explicit fields below still override anything."""

    # equipment-library selection (idealized model + optional calibrated unit by serial)
    manufacturer: Optional[str] = None  # e.g. "VICI"
    model: Optional[str] = None         # e.g. "M6"  (idealized 100 uL/rev nominal)
    serial: Optional[str] = None        # calibrated unit id, e.g. "M6-IN-0001"
    nickname: Optional[str] = None      # the unit's ID tag, e.g. "In pump"
    preset: Optional[str] = None        # legacy registry key, e.g. "VICI_M6_In" | "VICI_M50"
    name: Optional[str] = None          # PumpDelivery.name (also the cmds key)
    gain: Optional[float] = None
    beta: Optional[float] = None
    theta: Optional[float] = None
    tau_fast: Optional[float] = None
    w_slow: Optional[float] = None
    tau_slow: Optional[float] = None
    rho: Optional[float] = None
    carries_dye: Optional[bool] = None
    C_value: Optional[float] = None
    calibrated: Optional[bool] = None
    composition: Optional[dict[str, float]] = None    # species -> inlet conc (reactive runs)


class ReactorSpec(_Doc):
    """Which reactor module a node is (equipment-library provenance) + its materials. The resolved
    numeric config (geometry / rtd / temperature_K) lives directly on the NodeDoc; this records the
    chosen model/unit (so the GUI combos restore) and the two distinct materials."""

    manufacturer: Optional[str] = None      # e.g. "Generic"
    model: Optional[str] = None             # e.g. "PFA coil 1 mL" (idealized module)
    serial: Optional[str] = None            # calibrated unit id, e.g. "RX-PFA1-0001"
    nickname: Optional[str] = None          # the unit's tag, e.g. "Coil A"
    reactor_material: Optional[str] = None  # the block/housing, e.g. "aluminum"
    tube_material: Optional[str] = None     # the flow conduit, e.g. "PFA" | "FEP" | "stainless"


class InstrumentSpec(_Doc):
    """Which flow cell an instrument node is (equipment-library provenance) + its attachments.

    The node *is* the flow cell (the fluid passes through it); its resolved numeric config —
    cell volume (-> ``NodeDoc.V``) and optical ``path_length_mm`` — lives alongside. This records
    the chosen flow-cell make/model/unit (so the GUI combos restore) and the **spectrometer** +
    **light source** attachments selected on the cell, mirroring the reservoir's headspace feed.
    ``signal_kind``/``destructive`` classify how the instrument is observed (set by subtype)."""

    manufacturer: Optional[str] = None       # flow-cell make, e.g. "Generic"
    model: Optional[str] = None              # flow-cell model, e.g. "Z-flow 10 mm"
    serial: Optional[str] = None             # calibrated cell unit id, e.g. "FC-Z10-0001"
    nickname: Optional[str] = None           # the unit's tag
    path_length_mm: Optional[float] = None   # optical path length (Beer-Lambert) [mm]
    spectrometer: Optional[str] = None       # attachment make/model label (None = unspecified)
    light_source: Optional[str] = None       # attachment make/model label (None = unspecified)
    signal_kind: Optional[str] = None        # spectrum_vs_time | scalar_vs_time | sampled_trace
    destructive: bool = False                # sampled/destructive instrument (MS / HPLC)
    # Balance (gravimetric) technique fields — the balance measurement operator constants (BalanceConst)
    tare_g: Optional[float] = None           # post-tare baseline reading b0 [g]
    settle_window_s: Optional[float] = None  # averaging window W_b [s]
    settle_lag_s: Optional[float] = None     # settling lag tau_b [s]


class GeometrySpec(_Doc):
    """Explicit m6flow ``Geometry`` (exact). Defaults match ``m6flow.params.Geometry``."""

    R: float = 0.381
    A_c: float = 0.456
    L: float = 4715.0
    V_R: float = 2150.0


class TubingSpec(_Doc):
    """Friendly tubing description; geometry is computed (see registry.geometry_from_tubing)."""

    material: Optional[str] = None
    id_mm: float
    length_mm: float


class RtdSpec(_Doc):
    """RTD assignment for the analytical engine: model name + ordered params."""

    model: str = "plug"                  # default ideal plug flow; dispersive models set/regressed
    params: list[float] = []             # "plug" | "nCSTR" | "ADM" | "laminar"


class InletMixingSpec(_Doc):
    """Flow-ratio-dependent **poor-mixing mixer** (n-pump model, ch. 'Poor-Mixing Flow-Ratio
    Mixer'). What enters is always the flow-weighted blend; poor mixing instead gives the mixer
    its OWN n-CSTR RTD whose stage count degrades with the inlet flow ratio ``r = Q_in/Q``:

        n(r) = n_max * (4 r (1-r))**p

    (``n_max`` at equal flow r=1/2, p>0 the sharpness; n->0 == pass-through when one stream
    dominates). A node with ``inlet_mixing = None`` uses **perfect instantaneous inlet mixing**
    (the default RTD boundary condition)."""

    n_max: float = 10.0                  # stage count at equal flow (r = 1/2)
    p: float = 1.0                       # sharpness of the flow-ratio degradation (p > 0)


ContainerShape = Literal["media_bottle", "round_bottom_flask", "erlenmeyer", "vial"]
HeadspaceGas = Literal["air", "N2", "Ar", "CO2", "He", "other"]
HeadspaceFeed = Literal["open_ambient", "gas_cylinder", "balloon"]
OnEmpty = Literal["stop_run", "draw_gas"]            # multiphase gas-into-tubing is a future tier
ReservoirFidelity = Literal["boundary", "depletion"]
AMBIENT_K = 298.15


class ReservoirSpec(_Doc):
    """Enriched upstream-feed reservoir (DESIGN.md §7.1). Splits the old single ``composition``
    string into mixture / container / inventory / headspace / conditioning / behavior groups.

    Fidelity ``boundary`` (the default) reduces to the legacy infinite composition-only feed —
    Tier-0, byte-identical in the solver. ``depletion`` is Tier-1: a finite ``start_volume`` that
    drains as the downstream pump draws, with an ``on_empty`` policy. Transient transport (Tier-2)
    and per-feed thermal/multiphase effects are deferred; conditioning fields are stored metadata
    until the energy balance lands.
    """

    # --- Mixture: every named species is tracked with its starting concentration ---
    solvent: Optional[str] = None                 # role label: which species is the bulk liquid
    components: dict[str, float] = {}             # species -> starting concentration [mol/L]
    # --- Container ---
    shape: ContainerShape = "media_bottle"
    capacity: Optional[float] = None              # vessel volume [uL]
    # --- Inventory ---
    start_volume: Optional[float] = None          # starting liquid volume [uL]
    infinite: bool = True                         # infinite feed => Tier-0 boundary
    # --- Headspace ---
    headspace_gas: HeadspaceGas = "air"
    headspace_feed: Optional[HeadspaceFeed] = None  # default resolves by gas (see validator)
    # --- Conditioning (metadata until the energy balance lands) ---
    heated: bool = False
    temp_setpoint: Optional[float] = None         # [K]; the feed's starting temperature when heated
    stirred: bool = False                         # stirred => well-mixed (uniform c, T)
    # --- Behavior ---
    on_empty: OnEmpty = "stop_run"
    fidelity: ReservoirFidelity = "boundary"

    def feed_composition(self) -> dict[str, float]:
        """The tracked-species inlet concentrations this reservoir emits to its pump."""
        return dict(self.components)

    def feed_temperature(self) -> float:
        """Starting feed temperature [K]: the setpoint when heated, else ambient."""
        return self.temp_setpoint if (self.heated and self.temp_setpoint is not None) else AMBIENT_K

    @model_validator(mode="after")
    def _resolve(self) -> "ReservoirSpec":
        if self.headspace_feed is None:           # conditional default: air vents, inert blankets
            self.headspace_feed = "open_ambient" if self.headspace_gas == "air" else "balloon"
        if self.capacity is not None and self.start_volume is not None \
                and self.start_volume > self.capacity:
            raise ValueError("reservoir start_volume exceeds container capacity")
        if self.fidelity == "depletion" and not self.infinite and self.start_volume is None:
            raise ValueError("reservoir depletion fidelity requires a start_volume")
        return self


class NodeDoc(_Doc):
    """One flowsheet node. Per-type fields are optional; a validator checks requirements."""

    id: str
    type: NodeType
    subtype: Optional[str] = None               # reactor: spiral|serpentine; instrument: FTIR|HPLC
    display_name: Optional[str] = None          # user-facing label (defaults to id); renamable
    is_source: bool = False                     # "source" tag: marks a boundary feed (multi ok)
    # source / reservoir
    pump: Optional[PumpSpec] = None
    cmd_key: Optional[str] = None
    composition: Optional[dict[str, float]] = None   # reservoir feed (species -> conc); legacy/derived
    reservoir: Optional[ReservoirSpec] = None        # enriched reservoir model (mixture/inventory/...)
    # mixer / reactor
    V: Optional[float] = None
    geometry: Optional[GeometrySpec] = None
    tubing: Optional[TubingSpec] = None
    rtd: Optional[RtdSpec] = None
    inlet_mixing: Optional[InletMixingSpec] = None   # None = perfect inlet mixing (default)
    mixing_efficiency: Optional[float] = None        # [mixer] 0=segregated .. 1=perfect; a lumped
    #                                                  micromixing factor that scales downstream
    #                                                  reaction extent (None => 1.0, perfect)
    temperature_K: Optional[float] = None            # reactor isothermal setpoint (heated block);
    #                                                  None => fall back to the run's temperature
    radial_diffusion: Optional[float] = None         # [reactor, 2D tier] radial diffusion [mm^2/s];
    #   0 = segregated laminar .. large = radially uniform; molecular ~1e-3 is the Taylor-Aris regime
    reactor: Optional[ReactorSpec] = None            # reactor module provenance + materials
    instrument: Optional[InstrumentSpec] = None      # flow-cell provenance + spectrometer/lamp
    # splitter
    ratios: Optional[list[tuple[str, float]]] = None
    # selector valve
    selected: Optional[str] = None              # upstream node id whose stream is passed
    # separator (distillation / phase_separator)
    flow_ratios: Optional[list[tuple[str, float]]] = None         # outlet id -> flow fraction
    species_routes: Optional[dict[str, dict[str, float]]] = None  # outlet id -> {species: frac}
    default_outlet: Optional[str] = None
    # sink / collection / balance / instrument
    kind: Optional[str] = None
    # default operating point (a Run overrides); stored, not used by Phase-0 simulate
    defaults: Optional[dict[str, float]] = None

    def label(self) -> str:
        """The user-facing name (``display_name`` if set, else the stable ``id``)."""
        return self.display_name or self.id

    @model_validator(mode="after")
    def _require_per_type(self) -> "NodeDoc":
        t = self.type
        # reservoir: bridge the enriched spec to the legacy `composition` the Tier-0 build reads,
        # so a reservoir feed stays byte-identical whether authored old-style or with `reservoir`.
        if t == "reservoir" and self.reservoir is not None and self.composition is None:
            self.composition = self.reservoir.feed_composition() or None
        if t == "source" and self.pump is None:
            raise ValueError(f"source node {self.id!r} requires a `pump`")
        if t in ("mixer", "reactor"):
            if self.rtd is None:
                raise ValueError(f"{t} node {self.id!r} requires an `rtd`")
            if self.V is None and self.geometry is None and self.tubing is None:
                raise ValueError(f"{t} node {self.id!r} needs `V`, `geometry`, or `tubing`")
        if t == "splitter" and not self.ratios:
            raise ValueError(f"splitter node {self.id!r} requires `ratios`")
        return self


class EdgeDoc(_Doc):
    src: str
    dst: str
    dst_port: Optional[str] = None              # which input port the edge lands on (multi-inlet nodes,
    #                                             e.g. a tee mixer's in1/in2); None => the node's first
    tubing_material: Optional[str] = None       # "PFA" | "FEP" | "stainless"
    style: Optional[str] = None                 # pipe style hint ("solid" | "dashed" | ...)
    # tubing run for this connection -> holdup volume -> Tier-2 transport delay (tau = V/Q).
    # Both required for a delay; absent (the default) means an instantaneous edge (byte-identical).
    id_mm: Optional[float] = None               # tube inner diameter [mm]
    length_mm: Optional[float] = None           # tube length [mm]


class PlatformDoc(_Doc):
    """A reusable rig: topology + hardware attributes."""

    schema_version: str = "2.0"
    platform_id: str
    nodes: list[NodeDoc]
    edges: list[EdgeDoc]
