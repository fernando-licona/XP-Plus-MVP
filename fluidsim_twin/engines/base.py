"""Engine interface + result/capability DTOs (DESIGN.md §5).

One ``Engine`` protocol all fidelities satisfy. ``capabilities()`` validates a request
*before* a (possibly long) run; ``run()`` returns a ``SimResult``. Phase 0 ships only the
analytical engine; the protocol is the seam for the PDE/CFD engines in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, runtime_checkable

from numpy.typing import NDArray

from ..build import ResolvedFlowsheet


@dataclass
class CapabilityReport:
    """Whether an engine can serve a request, with reasons."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SimResult:
    """Forward-solve output. ``streams`` generalizes to multi-species in later phases."""

    t: NDArray                              # input grid [s]
    A: NDArray                              # cell absorbance on t
    tg: NDArray                             # internal uniform grid [s]
    cell_C: NDArray                         # cell composition on tg
    streams: dict[str, NDArray]             # node/stream label -> composition on tg
    delivered: dict[str, NDArray]           # pump.name -> delivered flow on tg [uL/min]
    mass: Optional[NDArray] = None          # cumulative delivered mass [g] on tg
    fidelity_used: str = "analytical_rtd"
    diagnostics: dict = field(default_factory=dict)
    species: Optional[dict] = None          # {"names": [...], "cell": (n_species, n_tg)} reactive
    # TRUE spatiotemporal composition field per transport unit (reactor): node id -> (n_species, n_z, n_tg),
    # with matching axial cell-centre coordinates in ``field_coords`` (node id -> (n_z,) [mm]). This is the
    # ground-truth state the TV-RTD equations are validated against; the flow cell only sees its average.
    fields: Optional[dict] = None
    field_coords: Optional[dict] = None
    signals: Optional[dict] = None          # instrument id -> observable at that analyzer's cell:
    #   {"subtype","kind","names","cell":(n_species,n_tg)}  (UV-4 adds spectral "axis"/"values")


ProgressFn = Callable[[float], None]
CancelFn = Callable[[], bool]


@runtime_checkable
class Engine(Protocol):
    """Structural interface for every simulation fidelity."""

    name: str
    supports_reaction: bool

    def capabilities(self, req: ResolvedFlowsheet) -> CapabilityReport: ...

    def run(self, req: ResolvedFlowsheet, *,
            progress: Optional[ProgressFn] = None,
            cancel: Optional[CancelFn] = None) -> SimResult: ...
