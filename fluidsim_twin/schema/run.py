"""RunDoc — operating conditions on a platform (DESIGN.md §7.2).

References a PlatformDoc and supplies the time grid, per-source command schedules
(ZOH breakpoints), species, observation (Beer-Lambert) parameters, and the fidelity.
Phase 0 handles the single passive-tracer, analytical-RTD case; reactions/overrides are
placeholders for later phases.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpeciesDoc(_Doc):
    name: str
    is_optical: bool = False
    inlet_default: float = 0.0


class GridSpec(_Doc):
    """Output time grid [s] for the forward solve: ``arange(t0, t_end, dt)``."""

    t0: float = 0.0
    t_end: float
    dt: float


class ScheduleDoc(_Doc):
    """Zero-order-hold command schedule: value ``values[i]`` holds from ``t_breaks[i]``."""

    t_breaks: list[float]
    values: list[float]


class ObservationDoc(_Doc):
    """Beer-Lambert observation: ``A = A_full * cell_C + offset``."""

    A_full: float = 1.0
    offset: float = 0.0


class FeatureDoc(_Doc):
    """One black-box model input, computed from the transport solution at the cell.

    kind: ``residence_time`` (s spent in ``node``), ``flow_fraction`` (sum of ``numerator``
    sources' delivered flow / sum of ``denominator`` sources', when the element entered
    ``node``), ``temperature`` (``node`` setpoint, degC) or ``constant`` (``value``).
    """

    name: str
    kind: str
    node: Optional[str] = None
    numerator: list[str] = []
    denominator: list[str] = []
    value: Optional[float] = None


class BlackBoxDoc(_Doc):
    """A data-driven output model evaluated on transport-resolved conditions (fidelity ``black_box``).

    ``model`` names a factory ``"package.module:callable"``; ``args`` are passed to it. The
    returned object has ``predict(X) -> (mean, std)`` with X rows ordered like ``features``.
    """

    model: str
    args: dict = {}
    features: list[FeatureDoc]
    outputs: list[str]


class RunDoc(_Doc):
    schema_version: str = "2.0"
    run_id: str
    platform_ref: str
    grid: GridSpec
    schedules: dict[str, ScheduleDoc]            # keyed by pump name (the cmds key)
    species: list[SpeciesDoc] = [SpeciesDoc(name="dye", is_optical=True)]
    observation: ObservationDoc = ObservationDoc()
    fidelity: str = "analytical_rtd"
    temperature_K: float = 298.15                # isothermal reactor temperature (Arrhenius) fallback
    # per-reactor temperature schedule [K], keyed by reactor node id. A single-breakpoint schedule
    # is a constant setpoint; multi-breakpoint is a (future) dynamic temperature ramp. Overrides the
    # node's own setpoint and the run-level temperature_K when present.
    temperature_schedules: dict[str, ScheduleDoc] = {}
    taud_of_Q: bool = False
    # per-source inlet composition override (species -> conc), keyed by source node id.
    # populated by the reaction library to load reactant A/B into chosen pumps for a run.
    feeds: dict[str, dict[str, float]] = {}
    # placeholders for later phases (kept so the doc family is complete)
    reactions: list[dict] = []
    overrides: dict[str, dict] = {}
    # third output option next to passive tracer and reaction kinetics: transport + a data model
    black_box: Optional[BlackBoxDoc] = None
