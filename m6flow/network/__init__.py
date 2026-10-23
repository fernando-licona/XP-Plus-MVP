"""Modular flow-graph (flowsheet) forward model: nodes + streams, solved by topo order.

See :mod:`m6flow.network.graph` for the node/stream types and :mod:`m6flow.network.solve`
for the flow + composition solver. Only acyclic graphs are solved this round (recycle is
a documented future extension).
"""
from __future__ import annotations

from .graph import (
    Analyzer, Flowsheet, Mixer, Passthrough, Reactor, Separator, Sink, Source, Splitter,
    Stream, case_study_3pump_flowsheet, grouped_3pump_flowsheet, lumped_2pump_flowsheet,
    three_pump_flowsheet,
)
from .driver import (GraphForwardReading, GraphSpeciesReading,
                     forward_absorbance_graph, forward_species_graph)
from .solve import (solve_cell_composition, solve_cell_species, solve_composition,
                    solve_composition_species, solve_flows)

__all__ = [
    "Flowsheet", "Source", "Mixer", "Reactor", "Analyzer", "Splitter", "Sink", "Stream",
    "Passthrough", "Separator",
    "lumped_2pump_flowsheet", "case_study_3pump_flowsheet", "three_pump_flowsheet",
    "grouped_3pump_flowsheet",
    "solve_flows", "solve_composition", "solve_cell_composition",
    "solve_composition_species", "solve_cell_species",
    "forward_absorbance_graph", "GraphForwardReading",
    "forward_species_graph", "GraphSpeciesReading",
]
