"""Gravimetric branch for the flowsheet: a Balance instrument node's weight reading r(t).

A **Balance** is a TERMINAL instrument technique — the stream is collected on a pan and weighed.
Its observable is the cumulative collected mass passed through the *validated balance measurement
operator* (``m6flow.forward.balance.reading_from_mass_rate``): the continuous settling response
(first-order lag ``tau_b`` convolved with the averaging window ``W_b``) with an optional ZOH latch
and readout quantum. This is the ``two_pump_model.tex`` "Gravimetric Branch", now attached to a node.

The mass-rate arriving on the pan is the flow-fraction of the total delivered mass rate
``Sum_p rho_p * Q_p`` that actually reaches the node (exact for a balance that collects the whole
effluent; a uniform-density approximation when a splitter feeds it only part of the stream).
"""
from __future__ import annotations

import numpy as np

from m6flow.forward.balance import reading_from_mass_rate
from m6flow.network.graph import Analyzer
from m6flow.network.solve import solve_flows


def is_balance_node(node) -> bool:
    """True for a Balance instrument (built as an :class:`Analyzer` with subtype ``Balance``)."""
    return isinstance(node, Analyzer) and (getattr(node, "subtype", "") or "").upper() == "BALANCE"


def build_balance_signals(fs, delivered: dict, tg, balance, balance_specs: dict | None = None) -> dict:
    """Signal entry per Balance node: the reading ``r(t)`` [g] on ``tg`` (``scalar_vs_time``).

    ``delivered`` maps each source pump name to its delivered flow on ``tg`` [uL/min]; ``balance``
    is the default :class:`~m6flow.params.BalanceConst`. ``balance_specs`` maps a node id to a
    per-node ``(BalanceConst, b0)`` (averaging window / settling lag / tare) from the node's fields.
    """
    bal = [n for n, nd in fs.nodes.items() if is_balance_node(nd)]
    if not bal:
        return {}
    tg = np.asarray(tg, float)
    specs = balance_specs or {}
    ef = solve_flows(fs, delivered, tg)                                  # per-edge flow [uL/min]
    pumps = [fs.nodes[n].pump for n in fs.sources()]
    rate = sum(p.rho * np.asarray(delivered[p.name], float) / 60.0 for p in pumps)   # g/s (total)
    q_total = sum(np.asarray(delivered[p.name], float) for p in pumps)               # uL/min (total)
    out: dict = {}
    for n in bal:
        ins = fs.in_edges(n)
        q_in = sum(ef[e] for e in ins) if ins else np.zeros_like(tg)
        frac = np.divide(q_in, q_total, out=np.zeros_like(q_in), where=q_total > 1e-12)
        mass_rate = rate * frac                                          # g/s onto this pan
        const, b0 = specs.get(n, (balance, 0.0))                         # per-node operator + tare
        r = reading_from_mass_rate(mass_rate, tg, const, b0=b0)          # g (settled reading)
        out[n] = {
            "subtype": "Balance", "kind": "balance",
            "signal_kind": "scalar_vs_time", "observable": "mass", "axis_unit": "s",
            "values": np.asarray(r, float),
        }
    return out
