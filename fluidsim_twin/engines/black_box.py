"""BlackBoxEngine — transport from the analytical TV-RTD engine, output from a data model.

The third output option next to the passive tracer (``analytical_rtd``) and mechanistic
kinetics (``reactive_pde``). Transport is solved exactly as the analytical engine does; then,
for every fluid element reaching the cell, its history is traced back along the flow path in
plug flow (mean element path): when it entered each unit, how long it stayed, and the stream
ratios it was made from. Those conditions are the model's inputs; the model's prediction is
the output. Dispersion around the mean path is not propagated through the model (fine near
plug flow; recorded in the diagnostics).
"""
from __future__ import annotations

import importlib
import json
from dataclasses import replace
from functools import lru_cache

import numpy as np

from m6flow.network.graph import Source, Stream

from ..build import ResolvedFlowsheet
from .analytical import AnalyticalRTDEngine
from .base import CapabilityReport, SimResult

KINDS = ("residence_time", "flow_fraction", "temperature", "constant")


@lru_cache(maxsize=8)
def _load(model: str, args_json: str):
    module, _, attr = model.partition(":")
    if not attr:
        raise ValueError(f"black-box model {model!r} must be 'package.module:callable'")
    return getattr(importlib.import_module(module), attr)(**json.loads(args_json))


def _ancestors(fs, name: str) -> set[str]:
    seen, stack = set(), [name]
    while stack:
        n = stack.pop()
        if n not in seen:
            seen.add(n)
            stack.extend(e.src for e in fs.in_edges(n))
    return seen


def _path_to_cell(fs, node: str, cell: str) -> list[str]:
    """Nodes from ``node`` to the cell, inclusive; requires a single downstream route."""
    path = [node]
    while path[-1] != cell:
        outs = fs.out_edges(path[-1])
        if len(outs) != 1:
            raise ValueError(f"black box: '{path[-1]}' has {len(outs)} outlets; "
                             f"needs one route from '{node}' to the cell")
        path.append(outs[0].dst)
        if len(path) > len(fs.nodes):
            raise ValueError("black box: cycle on the path to the cell")
    return path


def _volume(fs, name: str) -> float:
    n = fs.nodes[name]
    return float(n.geometry().V_R) if hasattr(n, "geometry") else 0.0


class _Tracer:
    """Plug-flow back-tracing of the element that reaches the cell at each grid time."""

    def __init__(self, req: ResolvedFlowsheet, tg: np.ndarray, delivered: dict):
        self.req, self.fs, self.tg, self.delivered = req, req.fs, tg, delivered
        self.cell = req.fs.cell()
        self._cum: dict[frozenset, np.ndarray] = {}

    def flow(self, names) -> np.ndarray:
        q = np.zeros_like(self.tg)
        for n in names:
            node = self.fs.nodes[n]
            if isinstance(node, Source):
                q = q + np.asarray(self.delivered[node.pump.name])
        return q

    def _sources_up(self, name: str) -> frozenset:
        return frozenset(n for n in _ancestors(self.fs, name) if isinstance(self.fs.nodes[n], Source))

    def _back(self, t_out: np.ndarray, volume: float, through: str) -> np.ndarray:
        """Entry time of the element leaving a segment of ``volume`` [uL] at ``t_out``."""
        if volume <= 0:
            return t_out
        key = self._sources_up(through)
        if key not in self._cum:
            q = self.flow(key) / 60.0  # uL/s
            self._cum[key] = np.concatenate([[0.0], np.cumsum(0.5 * (q[1:] + q[:-1]) * np.diff(self.tg))])
        vc = self._cum[key]
        target = np.interp(t_out, self.tg, vc) - volume
        t_in = np.interp(target, vc, self.tg)
        t_in[target < 0] = np.nan  # this fluid was already in the system at t = 0
        return t_in

    def times(self, node: str) -> tuple[np.ndarray, np.ndarray]:
        """(entry, exit) times at ``node`` of the element reaching the cell at each tg."""
        path = _path_to_cell(self.fs, node, self.cell)
        t = self.tg.copy()
        for up, down in reversed(list(zip(path[:-1], path[1:]))):
            geom = self.req.edge_geom.get(Stream(up, down))
            if geom is not None:
                t = self._back(t, float(geom.V_R), up)
            if up != node:
                t = self._back(t, _volume(self.fs, up), up)
        t_exit = t
        return self._back(t_exit, _volume(self.fs, node), node), t_exit

    def feature(self, f) -> np.ndarray:
        if f.kind == "constant":
            return np.full_like(self.tg, float(f.value))
        t_in, t_exit = self.times(f.node)
        if f.kind == "residence_time":
            return t_exit - t_in
        if f.kind == "temperature":
            prof = self.req.reactor_temperature_profiles.get(f.node)
            if prof is not None:
                return np.where(np.isnan(t_in), np.nan, np.asarray(prof(np.nan_to_num(t_in))) - 273.15)
            temp_k = self.req.reactor_temperatures.get(f.node, self.req.temperature_K)
            return np.where(np.isnan(t_in), np.nan, temp_k - 273.15)
        if f.kind == "flow_fraction":
            num, den = self.flow(f.numerator), self.flow(f.denominator)
            ratio = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)
            out = np.interp(np.nan_to_num(t_in), self.tg, ratio)
            return np.where(np.isnan(t_in), np.nan, out)
        raise ValueError(f"unknown black-box feature kind {f.kind!r}")


class _Linear:
    def __init__(self, weights, bias):
        self.W, self.b = np.asarray(weights, float), np.asarray(bias, float)

    def predict(self, X):
        mean = np.asarray(X) @ self.W.T + self.b
        return mean, np.zeros_like(mean)


def linear_model(weights: list[list[float]], bias: list[float]):
    """Built-in black box y = W x + b (tests, demos; ``fluidsim_twin.engines.black_box:linear_model``)."""
    return _Linear(weights, bias)


class BlackBoxEngine:
    """Analytical transport + a pluggable data-driven output model."""

    name = "black_box"
    supports_reaction = False

    def capabilities(self, req: ResolvedFlowsheet) -> CapabilityReport:
        errors: list[str] = []
        bb = req.black_box
        if bb is None:
            return CapabilityReport(ok=False, errors=["black_box fidelity needs run.black_box"])
        errors += AnalyticalRTDEngine().capabilities(req).errors
        for f in bb.features:
            if f.kind not in KINDS:
                errors.append(f"feature {f.name!r}: unknown kind {f.kind!r}")
            if f.kind == "constant" and f.value is None:
                errors.append(f"feature {f.name!r}: constant needs a value")
            for n in ([f.node] if f.kind != "constant" else []) + list(f.numerator) + list(f.denominator):
                if n not in req.fs.nodes:
                    errors.append(f"feature {f.name!r}: unknown node {n!r}")
            if f.kind != "constant" and f.node in req.fs.nodes:
                try:
                    _path_to_cell(req.fs, f.node, req.fs.cell())
                except ValueError as exc:
                    errors.append(str(exc))
        return CapabilityReport(ok=not errors, errors=errors)

    def run(self, req: ResolvedFlowsheet, *, progress=None, cancel=None) -> SimResult:
        rep = self.capabilities(req)
        if not rep.ok:
            raise ValueError("; ".join(rep.errors))
        base = AnalyticalRTDEngine().run(req, progress=progress, cancel=cancel)
        bb = req.black_box
        tracer = _Tracer(req, np.asarray(base.tg), base.delivered)
        feats = {f.name: tracer.feature(f) for f in bb.features}
        X = np.column_stack([feats[f.name] for f in bb.features])
        ok = np.all(np.isfinite(X), axis=1)
        mean = np.full((len(bb.outputs), X.shape[0]), np.nan)
        std = np.full_like(mean, np.nan)
        if ok.any():
            model = _load(bb.model, json.dumps(bb.args, sort_keys=True))
            m, s = model.predict(X[ok])
            mean[:, ok], std[:, ok] = np.asarray(m).T, np.asarray(s).T
        cell = req.fs.cell()
        signals = dict(base.signals or {})
        signals[f"{cell}:black_box"] = {"kind": "black_box", "names": list(bb.outputs),
                                        "cell": mean, "std": std, "features": feats}
        diagnostics = {**base.diagnostics, "black_box_model": bb.model,
                       "black_box_valid_fraction": float(ok.mean()),
                       "black_box_path": "plug-flow mean element path (dispersion not propagated)"}
        return replace(base, fidelity_used=self.name, signals=signals, diagnostics=diagnostics)
