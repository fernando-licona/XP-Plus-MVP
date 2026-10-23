"""Optical branch: the four time-varying residence-time-distribution (TV-RTD) models.

Implements ``two_pump_model.tex`` Chapters "The Adjoint Fokker-Planck Foundation",
"The Four Lumped TV-RTD Models", and the optical observation. The cell dye fraction
is the RTD-smeared inlet fraction

    r_cell(t) = integral_0^inf f_in(t-alpha) E(alpha,t) d(alpha),

evaluated in swept-volume coordinates. Four closed-form ``E`` are provided: plug
(pure volume delay), n-CSTR (Gamma in the integrated volumetric age ``Phi``), ADM
(Gaussian in swept volume), and laminar + Taylor-Aris (flow-dependent dispersion).

.. important::
   **This module works in MINUTES.** Inputs arrive in seconds and are converted
   exactly once, in :meth:`FlowField.__init__`, via :func:`m6flow.units.minutes`.
   Flows are ``uL/min``, volumes ``uL``; the dispersion groupings carry diffusivity
   in ``mm^2/min`` (``a = 2 A_c^2 Dbar11``, ``b = R^2/(24 D22)``).

Numerics ported from ``previous-work/tvrtd_repro.py`` (``Sys`` -> :class:`FlowField`;
``rcell_plug``/``rcell_ncstr``/``rcell_disp``; ``D_from_a``/``D22_from_b``).
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.special import gammaln

from .. import units
from ..params import Geometry, DEFAULT_GEOMETRY


class FlowField:
    """Flow-derived quantities precomputed on a uniform grid (MINUTES).

    Precomputes, once, everything the RTD kernels need: total flow ``Q``, inlet
    fraction ``fin``, cumulative swept volume ``Vcum`` [uL], and the running
    ``Wq = cumsum(Q^2 dt)`` used by the Taylor term.

    Parameters
    ----------
    t_s : ndarray
        Time grid in **seconds** (uniform). Converted to minutes internally.
    In, P : ndarray
        Delivered In/P flows [uL/min] on ``t_s``.
    geom : Geometry
        Reactor geometry (provides ``V_R``).
    """

    def __init__(self, t_s: NDArray, In: NDArray, P: NDArray, geom: Geometry = DEFAULT_GEOMETRY):
        self.geom = geom
        dt_s = float(np.median(np.diff(t_s)))
        self.dt_min = float(units.minutes(dt_s))          # the one seconds->minutes crossing
        Q = np.asarray(In, float) + np.asarray(P, float)
        self.Q = Q
        self.fin = np.where(Q > 1e-6, np.asarray(In, float) / np.where(Q > 1e-6, Q, 1.0), 0.0)
        dV = Q * self.dt_min                              # uL delivered per sample
        self.Vcum = np.cumsum(dV) - dV                    # cumulative volume before sample i
        self.Wq = np.cumsum(Q * Q * self.dt_min) - Q * Q * self.dt_min
        self.N = len(t_s)

    @classmethod
    def from_flow(cls, t_s: NDArray, Q: NDArray, geom: Geometry = DEFAULT_GEOMETRY,
                  *, fin: NDArray | None = None) -> "FlowField":
        """Build a field from an arbitrary stage flow ``Q`` and carried signal ``fin``.

        Used by the multi-stage / flow-graph solver where a node's flow is the
        accumulated upstream flow (not ``In+P``) and the carried composition is the
        upstream output (not ``In/Q``). With ``Q = In+P`` and ``fin = In/Q`` this
        reproduces ``FlowField(t, In, P, geom)`` field-for-field.
        """
        self = cls.__new__(cls)
        self.geom = geom
        dt_s = float(np.median(np.diff(t_s)))
        self.dt_min = float(units.minutes(dt_s))
        Q = np.asarray(Q, float)
        self.Q = Q
        self.fin = np.zeros_like(Q) if fin is None else np.asarray(fin, float)
        dV = Q * self.dt_min
        self.Vcum = np.cumsum(dV) - dV
        self.Wq = np.cumsum(Q * Q * self.dt_min) - Q * Q * self.dt_min
        self.N = len(t_s)
        return self


def rcell_plug(ff: FlowField, signal: NDArray | None = None, decay: float = 0.0) -> NDArray:
    """Plug-flow cell fraction: pure delay by one reactor volume ``V_R``.

    The parcel exiting at ``t`` entered when the cumulative volume was ``Vcum - V_R``;
    the carried composition is read there. ``signal`` overrides ``ff.fin`` (the inlet
    composition for a non-source stage); ``None`` uses ``ff.fin`` (byte-identical).
    ``decay`` is a first-order rate [1/min]: each parcel is multiplied by
    ``exp(-decay * age)`` (exact first-order kinetics); ``decay=0`` is byte-identical.
    """
    src = ff.fin if signal is None else signal
    target = ff.Vcum - ff.geom.V_R
    out = np.interp(target, ff.Vcum, src, left=src[0])
    if decay:
        idxg = np.arange(ff.N, dtype=float)
        entry = np.interp(target, ff.Vcum, idxg, left=0.0)
        out = out * np.exp(-decay * (idxg - entry) * ff.dt_min)
    return out


def rcell_ncstr(ff: FlowField, n: float, ksub: int = 4, signal: NDArray | None = None,
                decay: float = 0.0) -> NDArray:
    """n-CSTR cell fraction: a Gamma law of shape ``n`` in the volumetric age ``Phi``.

    The Gamma kernel integrates to one over the full age support, so the deficit at
    start-up (history reaching before ``t=0``) correctly maps to the dye-free
    pre-fill (``f_in=0``); no renormalisation to the truncated window is applied.
    ``ksub`` subsamples the output grid (the kernel is smooth) for speed. ``decay`` is a
    first-order rate [1/min]: each age-``alpha`` contribution is weighted by
    ``exp(-decay*alpha)`` (``decay=0`` is byte-identical).
    """
    src = ff.fin if signal is None else signal
    V_R = ff.geom.V_R
    sigV = V_R / np.sqrt(max(n, 1.0))
    Vmax = V_R + 8.0 * sigV
    N = ff.N
    out = np.empty(N)
    logn = np.log(n)
    lg = gammaln(n)
    idx = np.arange(0, N, ksub)
    for i in idx:
        lo = np.searchsorted(ff.Vcum, ff.Vcum[i] - Vmax)
        j = np.arange(lo, i + 1)
        if len(j) < 2:
            out[i] = 0.0
            continue
        Vsw = ff.Vcum[i] - ff.Vcum[j]
        Phi = Vsw / V_R
        with np.errstate(divide="ignore"):
            logw = logn + (n - 1) * np.log(np.maximum(n * Phi, 1e-300)) - lg - n * Phi
        w = np.exp(logw) * (ff.Q[j] / V_R) * ff.dt_min     # E(alpha) d(alpha), mass ~ 1
        if decay:
            w = w * np.exp(-decay * (i - j) * ff.dt_min)
        out[i] = float((w * src[j]).sum())                 # deficit -> pre-fill comp 0
    if ksub > 1:
        out = np.interp(np.arange(N), idx, out[idx])
    return out


def rcell_dispersion(ff: FlowField, a: float, b: float = 0.0, ksub: int = 4,
                     signal: NDArray | None = None, decay: float = 0.0) -> NDArray:
    """ADM (``b=0``) / laminar (``b>0``) cell fraction: a Gaussian in swept volume.

    ``E(alpha,t) ~ exp(-(Vsw-V_R)^2 / W) / sqrt(pi W)``, with
    ``W = integral (a + b Q^2) dt`` and the distribution normalised over age (the
    ``two_pump_model.tex`` plug-with-dispersion TV-RTD). ``a = 2 A_c^2 Dbar11``,
    ``b = R^2/(24 D22)`` (minutes / mm units). ``decay`` is a first-order rate [1/min]:
    the normalised RTD is weighted by ``exp(-decay*alpha)`` (``decay=0`` byte-identical).
    """
    src = ff.fin if signal is None else signal
    V_R = ff.geom.V_R
    pos = ff.Q > 10
    Qmed = float(np.median(ff.Q[pos])) if pos.any() else 1.0
    tau = V_R / Qmed
    Wtyp = a * tau + b * Qmed * Qmed * tau
    Vmax = V_R + 12.0 * np.sqrt(max(Wtyp, 1.0))
    N = ff.N
    out = np.zeros(N)
    idx = np.arange(0, N, ksub)
    for i in idx:
        lo = np.searchsorted(ff.Vcum, ff.Vcum[i] - Vmax)
        j = np.arange(lo, i + 1)
        if len(j) < 2:
            out[i] = 0.0
            continue
        Vsw = ff.Vcum[i] - ff.Vcum[j]
        alpha = (i - j) * ff.dt_min
        W = np.maximum(a * alpha + b * (ff.Wq[i] - ff.Wq[j]), 1e-12)
        d = Vsw - V_R
        g = np.exp(-d * d / W) / np.sqrt(np.pi * W)
        sg = g.sum()
        wsrc = g * src[j]
        if decay:
            wsrc = wsrc * np.exp(-decay * alpha)
        out[i] = float(wsrc.sum() / sg) if sg > 0 else 0.0
    if ksub > 1:
        out = np.interp(np.arange(N), idx, out[idx])
    return out


def rcell_poormix(ff: FlowField, n_max: float, p: float, r: NDArray,
                  signal: NDArray | None = None, decay: float = 0.0) -> NDArray:
    """Flow-ratio-dependent **poor-mixing mixer** RTD (n-pump model, ch. 'Poor-Mixing Flow-Ratio
    Mixer', Eq. ms-mixer-rtd). The mixer is a single time-varying CSTR whose flushing rate scales
    with the inlet mixing quality

        n(r) = n_max * (4 r (1-r))**p,      k(t) = n(r(t)) Q(t) / V_M     [1/min],

    so the exit-age density is ``E_M(alpha,t) = k(t-alpha) exp(-int_{t-alpha}^t k)``. The outlet
    ``X(t) = int C_in(t-alpha) E_M dalpha`` therefore obeys exactly ``dX/dt = k(t)(C_in - X)`` --
    a well-mixed tank relaxing toward the (flow-weighted) inlet at rate ``k``. Integrated with the
    exact exponential step (stable for any ``k*dt``); the start-up deficit maps to the dye-free
    pre-fill ``X(t<=0)=0`` (matching the other kernels). ``r`` is the inlet flow ratio Q_a/Q per
    sample; ``decay`` adds a first-order sink ``-decay*X`` (``decay=0`` is the passive tracer).
    Good mixing (n>1) shortens/sharpens the RTD; poor mixing (n<1) broadens it.
    """
    src = ff.fin if signal is None else np.asarray(signal, float)
    V_M = ff.geom.V_R
    if V_M <= 0.0:                                    # zero-volume mixer -> instantaneous blend
        return np.array(src, float)
    rr = np.clip(np.asarray(r, float), 0.0, 1.0)
    n = float(n_max) * np.power(np.clip(4.0 * rr * (1.0 - rr), 0.0, 1.0), float(p))
    k = n * ff.Q / V_M                                # flushing rate [1/min]
    keff = k + float(decay)
    a = np.exp(-keff * ff.dt_min)                     # exact decay over one step
    with np.errstate(divide="ignore", invalid="ignore"):
        target = np.where(keff > 0.0, k * src / np.where(keff > 0.0, keff, 1.0), src)
    out = np.empty(ff.N)
    x = 0.0                                           # dye-free pre-fill (start-up deficit BC)
    for i in range(ff.N):
        x = target[i] + (x - target[i]) * a[i]        # k=0 -> x held (no flushing)
        out[i] = x
    return out


def plug_age(ff: FlowField) -> NDArray:
    """Residence age [min] of the parcel exiting at each time, from flow history (``Phi=1``).

    The parcel exiting at ``t`` entered when the cumulative swept volume was ``Vcum - V_R``;
    its age is the elapsed time back to that entry. This is the flow-history-aware residence
    time used by the dynamic-experiment mapping (DFE); for slow ramps it reduces to ``V/Q``.
    """
    target = ff.Vcum - ff.geom.V_R
    idxg = np.arange(ff.N, dtype=float)
    entry = np.interp(target, ff.Vcum, idxg, left=0.0)
    return (idxg - entry) * ff.dt_min


def D_from_a(a: float, geom: Geometry = DEFAULT_GEOMETRY) -> float:
    """Convert the ADM grouping ``a = 2 A_c^2 Dbar11`` to ``Dbar11`` [cm^2/s]."""
    return units.D_mm2min_to_cm2s(a / (2.0 * geom.A_c ** 2))


def D22_from_b(b: float, geom: Geometry = DEFAULT_GEOMETRY) -> float:
    """Convert the laminar grouping ``b = R^2/(24 D22)`` to ``D22`` [cm^2/s]."""
    if b <= 0:
        return float("inf")
    return units.D_mm2min_to_cm2s(geom.R ** 2 / (24.0 * b))


#: name -> (callable(ff, *params) -> r_cell, ordered param names) for the four models.
RTD_MODELS: dict[str, tuple] = {
    "plug": (lambda ff: rcell_plug(ff), ()),
    "nCSTR": (lambda ff, n: rcell_ncstr(ff, n), ("n",)),
    "ADM": (lambda ff, a: rcell_dispersion(ff, a, 0.0), ("a",)),
    "laminar": (lambda ff, a, b: rcell_dispersion(ff, a, b), ("a", "b")),
}
