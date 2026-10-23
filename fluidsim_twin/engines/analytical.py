"""AnalyticalRTDEngine — a thin, loss-free wrapper over m6flow's flow-graph forward map.

For the single passive-tracer case this is *exactly* ``forward_absorbance_graph``; the
engine adds no physics, so it reproduces the validated m6flow path byte-for-byte. Reactive
chemistry and the other fidelities arrive in later phases (DESIGN.md §5.1).
"""
from __future__ import annotations

from m6flow.network.driver import forward_absorbance_graph

from ..build import ResolvedFlowsheet
from ..optical import build_instrument_signals
from .base import CapabilityReport, Engine, SimResult


class AnalyticalRTDEngine:
    """Analytical TV-RTD engine (m6flow). Passive tracer only in Phase 0."""

    name = "analytical_rtd"
    supports_reaction = False

    def capabilities(self, req: ResolvedFlowsheet) -> CapabilityReport:
        errors: list[str] = []
        warnings: list[str] = []
        if len(req.species) > 1:
            errors.append("analytical engine handles a single passive tracer in Phase 0 "
                          f"(got species {req.species})")
        return CapabilityReport(ok=not errors, errors=errors, warnings=warnings)

    def run(self, req: ResolvedFlowsheet, *, progress=None, cancel=None) -> SimResult:
        rep = self.capabilities(req)
        if not rep.ok:
            raise ValueError("; ".join(rep.errors))
        if progress is not None:
            progress(0.0)
        taps: dict = {}
        gr = forward_absorbance_graph(
            req.t, req.cmds, req.fs,
            A_full=req.A_full, offset=req.offset,
            balance=req.balance, taud_of_Q=req.taud_of_Q,
            edge_geom=req.edge_geom, taps_out=taps,
        )
        if progress is not None:
            progress(1.0)
        cell_label = req.fs.cell()
        signals = build_instrument_signals(req.fs, taps, list(req.species),
                                           getattr(req, "instrument_specs", {}),
                                           optical_models=getattr(req, "optical_models", None))
        from ..gravimetric import build_balance_signals               # Balance nodes -> weight reading r(t)
        signals = {**(signals or {}), **build_balance_signals(req.fs, gr.delivered, gr.tg, req.balance, getattr(req, "balance_specs", None))}
        return SimResult(
            t=req.t, A=gr.A, tg=gr.tg, cell_C=gr.cell_C,
            streams={cell_label: gr.cell_C},
            delivered=gr.delivered, mass=gr.mass,
            fidelity_used=self.name,
            diagnostics={"n_tg": int(gr.tg.size)},
            signals=(signals or None),
        )


# satisfy the structural Engine protocol at import time (cheap guard)
_engine: Engine = AnalyticalRTDEngine()
