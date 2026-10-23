"""Gravimetric branch: the balance measurement operator.

Implements ``two_pump_model.tex`` Chapter "Gravimetric Branch: the Balance
Measurement Operator". The operator has three stages applied to the true cumulative
mass on the pan:

1. **continuous smoothing** ``G(s) = e^{-theta_b s}/(1+tau_b s) * (1-e^{-W_b s})/(W_b s)``,
   whose closed-form step response is :func:`step_response`;
2. a **zero-order-hold latch** at ``f_ref`` (:func:`zoh_latch`);
3. **quantisation** to the readout quantum ``q`` (:func:`quantize`).

The validated cumulative-mass fit uses only the continuous stage (the latch and
quantum are negligible in the low-frequency band), so :func:`reading_from_mass_rate`
defaults to continuous-only and exposes the latch/quantise stages as opt-in flags.

All quantities are in **seconds** / **grams**. Numerics ported from
``previous-work/toolset.py`` (``Sfun``, ``balance_kernel``, ``forward_reading``).
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import fftconvolve

from ..params import BalanceConst


def step_response(x_s: NDArray, W: float, tau: float) -> NDArray:
    """Continuous balance step response ``S(x)`` (boxcar of width ``W`` (x) lag ``tau``).

    Closed form (``two_pump_model.tex`` Eq. balance step response): zero for ``x<0``,
    a lag-smoothed ramp of slope ``1/W`` for ``0<=x<W``, settling for ``x>=W``.
    """
    x = np.asarray(x_s, float)
    o = np.zeros_like(x)
    a = (x >= 0) & (x < W)
    o[a] = x[a] / W - (tau / W) * (1.0 - np.exp(-x[a] / tau))
    b = x >= W
    o[b] = 1.0 - (tau / W) * (np.exp(-(x[b] - W) / tau) - np.exp(-x[b] / tau))
    return o


def smoothing_kernel(n: int, db: float, W: float, tau: float) -> NDArray:
    """Sampled step response on an ``n``-point grid of spacing ``db`` (the conv kernel)."""
    return step_response(np.arange(n) * db, W, tau)


def continuous_estimate(mass_rate_gs: NDArray, db: float, W: float, tau: float) -> NDArray:
    """The balance's internal continuous estimate ``y(t) = (G * M)(t)`` [g].

    Convolving the mass *rate* ``dM/dt`` with the step response ``S`` equals
    convolving the cumulative mass ``M`` with the impulse response ``g = dS/dx``
    (integration by parts), so this returns ``(G * M)(t)`` directly.
    """
    n = len(mass_rate_gs)
    S = smoothing_kernel(n, db, W, tau)
    return db * fftconvolve(mass_rate_gs, S)[:n]


def zoh_latch(y: NDArray, tg: NDArray, f_ref: float) -> NDArray:
    """Zero-order-hold: sample ``y`` on a fixed ``f_ref`` clock and hold between updates.

    When ``tg`` is already the latch grid (spacing ``1/f_ref``) this is the identity;
    implemented generally so a finer ``tg`` is handled correctly.
    """
    dlatch = 1.0 / f_ref
    latch_t = np.arange(tg[0], tg[-1] + dlatch, dlatch)
    latch_y = np.interp(latch_t, tg, y)
    idx = np.clip(np.searchsorted(latch_t, tg, side="right") - 1, 0, len(latch_t) - 1)
    return latch_y[idx]


def quantize(x: NDArray, q: float) -> NDArray:
    """Round ``x`` to the readout quantum ``q`` [g]."""
    return q * np.round(np.asarray(x, float) / q)


def reading_from_mass_rate(
    mass_rate_gs: NDArray,
    tg: NDArray,
    balance: BalanceConst,
    b0: float = 0.0,
    *,
    latch: bool = False,
    quantise: bool = False,
) -> NDArray:
    """Reported balance reading from a mass-rate signal on grid ``tg`` [g].

    Parameters
    ----------
    mass_rate_gs : ndarray
        Mass delivery rate ``dM/dt`` on ``tg`` [g/s].
    tg : ndarray
        Uniform time grid [s] (spacing ``balance.db``).
    balance : BalanceConst
        Balance operator constants.
    b0 : float
        Post-tare baseline reading [g].
    latch, quantise : bool
        Apply the ZOH latch and/or the quantiser. Both default False to reproduce the
        validated continuous-smoothing cumulative-mass fit.
    """
    y = continuous_estimate(mass_rate_gs, balance.db, balance.W_b, balance.tau_b)
    if latch:
        y = zoh_latch(y, tg, balance.f_ref)
    if quantise:
        y = quantize(y, balance.q)
    return y + b0
