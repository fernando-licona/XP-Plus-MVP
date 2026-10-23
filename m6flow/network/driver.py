"""End-to-end forward driver for a flow graph: commands -> cell absorbance (+ mass).

Composes the delivery sub-models, the topological flow/composition solve, and the
Beer-Lambert observation. The gravimetric branch sums each stream's delivered mass with
its own density (so a multi-material 3-pump run is handled); for the single-material
2-pump case this matches the validated `forward_reading` mass.

All time quantities in **seconds**; flows in ``uL/min``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import cumulative_trapezoid

from ..forward.delivery import delivered_flows
from ..forward.observation import beer_lambert
from ..params import BalanceConst, DEFAULT_BALANCE
from .graph import Flowsheet, Source
from .solve import (solve_cell_composition, solve_cell_species, solve_composition,
                    solve_flows)


@dataclass
class GraphForwardReading:
    """Result of the flow-graph forward map."""

    A: NDArray                         # predicted cell absorbance on the input grid ``t``
    tg: NDArray                        # internal uniform grid [s]
    cell_C: NDArray                    # cell composition (dye level) on ``tg``
    delivered: dict                    # pump name -> delivered flow on ``tg`` [uL/min]
    mass: NDArray = field(repr=False, default=None)   # cumulative delivered mass [g] on tg


def forward_absorbance_graph(t: NDArray, cmds: dict[str, NDArray], fs: Flowsheet, *,
                             A_full: float, offset: float, balance: BalanceConst = DEFAULT_BALANCE,
                             taud_of_Q: bool = False,
                             node_ops: dict | None = None,
                             edge_geom: dict | None = None,
                             taps_out: dict | None = None) -> GraphForwardReading:
    """Predict the optical-cell absorbance from per-pump command schedules.

    Parameters
    ----------
    t : ndarray
        Input time grid [s].
    cmds : mapping
        ``pump.name -> commanded flow on t`` [uL/min] for every source in ``fs``.
    fs : Flowsheet
        The (acyclic) flow graph.
    A_full, offset : float
        Beer-Lambert slope and dye-free baseline.
    """
    t = np.asarray(t, float)
    tg = np.arange(t[0], t[-1], balance.db)
    pumps = [fs.nodes[n].pump for n in fs.sources()]
    cmd_g = {p.name: np.interp(tg, t, cmds[p.name]) for p in pumps}
    delivered = delivered_flows(tg, cmd_g, pumps, balance.db, taud_of_Q=taud_of_Q)

    cell_C = solve_cell_composition(fs, delivered, tg, node_ops=node_ops, edge_geom=edge_geom,
                                    taps_out=taps_out)
    A = beer_lambert(cell_C, A_full, offset)

    # gravimetric branch: total delivered mass = sum_j rho_j * integral(Q_j/60)
    rate = sum(p.rho * delivered[p.name] / 60.0 for p in pumps)
    mass = cumulative_trapezoid(rate, tg, initial=0.0)

    return GraphForwardReading(A=np.interp(t, tg, A), tg=tg, cell_C=cell_C,
                               delivered=delivered, mass=mass)


@dataclass
class GraphSpeciesReading:
    """Result of the multi-species flow-graph forward map."""

    A: NDArray                         # predicted absorbance (optical species) on the input grid
    tg: NDArray                        # internal uniform grid [s]
    species: list                      # ordered species names (row order of ``cell``)
    cell: NDArray                      # cell species field, shape (n_species, len(tg))
    cell_C: NDArray                    # the optical species' row (convenience; on tg)
    delivered: dict                    # pump name -> delivered flow on tg [uL/min]
    mass: NDArray = field(repr=False, default=None)   # cumulative delivered mass [g] on tg


def forward_species_graph(t: NDArray, cmds: dict[str, NDArray], fs: Flowsheet, *,
                          species: list, A_full: float, offset: float,
                          optical_species: str = "dye", source_comp: dict | None = None,
                          balance: BalanceConst = DEFAULT_BALANCE, taud_of_Q: bool = False,
                          node_ops: dict | None = None,
                          edge_geom: dict | None = None,
                          taps_out: dict | None = None) -> GraphSpeciesReading:
    """Multi-species forward map: per-pump commands -> full cell species field + absorbance.

    The species generalisation of :func:`forward_absorbance_graph`. Each source emits its
    per-species inlet vector (``source_comp[node_id]`` overrides, else the source pump's
    :meth:`~m6flow.params.PumpDelivery.species_composition`); reactions enter through a
    reactive ``node_ops`` operator on the reactor node(s). The optical observation reads the
    ``optical_species`` row by Beer-Lambert, so a single ``"dye"`` species reproduces the
    scalar :func:`forward_absorbance_graph` exactly.
    """
    t = np.asarray(t, float)
    tg = np.arange(t[0], t[-1], balance.db)
    pumps = [fs.nodes[n].pump for n in fs.sources()]
    cmd_g = {p.name: np.interp(tg, t, cmds[p.name]) for p in pumps}
    delivered = delivered_flows(tg, cmd_g, pumps, balance.db, taud_of_Q=taud_of_Q)

    comp = {n: fs.nodes[n].pump.species_composition() for n in fs.sources()}
    if source_comp:
        for n, c in source_comp.items():
            comp[n] = dict(c)

    cell = solve_cell_species(fs, delivered, tg, list(species), comp,
                              node_ops=node_ops, edge_geom=edge_geom, taps_out=taps_out)
    if cell is None:                              # rig has no optical cell (collection-only)
        cell = np.zeros((len(species), len(tg)))
    oidx = list(species).index(optical_species) if optical_species in species else 0
    cell_C = cell[oidx]
    A = beer_lambert(cell_C, A_full, offset)

    rate = sum(p.rho * delivered[p.name] / 60.0 for p in pumps)
    mass = cumulative_trapezoid(rate, tg, initial=0.0)

    return GraphSpeciesReading(A=np.interp(t, tg, A), tg=tg, species=list(species),
                               cell=cell, cell_C=cell_C, delivered=delivered, mass=mass)
