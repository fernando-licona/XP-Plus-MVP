"""DC-FOPDT delivery model: pump commands -> delivered volumetric flow.

Implements ``two_pump_model.tex`` Chapters "Hardware Grounding", "From the Actuation
Chain to a First-Order Lag", and "The Validated Delivery Model". The delivered flow
of pump ``p`` is

    Q_del_p = L[ T_theta_p( g_p(Q_cmd) * Q_cmd ) ],

with the turbulent-backpressure gain ``g_bp`` (``g_In = g0 g_bp``, ``g_P = aP
g_bp``), a per-pump pure dead time ``T_theta``, and the parallel fast/slow
first-order lag ``L``.

All quantities here are in **seconds**; flows are in ``uL/min``. Inputs are assumed
to be sampled on a uniform grid of spacing ``db`` seconds (the balance latch grid);
callers interpolate raw commands onto that grid (see
:func:`m6flow.forward.assembly.forward_reading`).

Ported verbatim (numerics) from ``previous-work/toolset.py``.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.signal import lfilter

from ..params import DeliveryParams, PumpDelivery


def g_bp(Q: NDArray | float, beta: float) -> NDArray:
    """Turbulent-backpressure gain ``g_bp(Q) = (-1 + sqrt(1 + 4 beta Q)) / (2 beta Q)``.

    The single-parameter steady-state delivered/commanded ratio implied by a
    pressure drop scaling as ``Q^2`` (``two_pump_model.tex`` Eq. backpressure gain).
    Clipped at a tiny positive flow to keep the ``0/0`` limit (``-> 1``) well behaved.

    At ``beta -> 0`` (an ideal / backpressure-free pump) the ratio approaches 1
    (delivered == commanded); the closed form is a ``0/0`` there, so return the limit
    directly instead of dividing by ``2 beta Q == 0`` (which would yield NaN).
    """
    Q = np.maximum(np.asarray(Q, float), 1e-9)
    if beta <= 0.0:
        return np.ones_like(Q)
    return (-1.0 + np.sqrt(1.0 + 4.0 * beta * Q)) / (2.0 * beta * Q)


def first_order_lag(f: NDArray, tau: float, db: float) -> NDArray:
    """Unit-gain first-order lag of a sampled signal ``f`` (time constant ``tau`` [s]).

    Discrete realization of ``tau y' + y = f`` on a grid of spacing ``db`` via a
    one-pole IIR filter.
    """
    a = 1.0 - np.exp(-db / tau)
    return lfilter([a], [1.0, -(1.0 - a)], f)


def varying_lag(f: NDArray, tau_arr: NDArray, db: float) -> NDArray:
    """First-order lag with a per-sample time constant ``tau_arr`` [s].

    Used by the alternative flow-dependent-lag delivery variant ``tau_d(Q)``.
    """
    a = 1.0 - np.exp(-db / np.maximum(tau_arr, 1e-6))
    y = np.zeros_like(f)
    prev = 0.0
    for i in range(len(f)):
        prev = prev + a[i] * (f[i] - prev)
        y[i] = prev
    return y


def deadtime(f: NDArray, tg: NDArray, theta: float) -> NDArray:
    """Pure transport delay: shift ``f`` (defined on grid ``tg``) by ``theta`` seconds."""
    return np.interp(tg - theta, tg, f, left=0.0)


def two_lag(f: NDArray, p: DeliveryParams, db: float) -> NDArray:
    """Parallel fast/slow first-order lag ``(1-w) FO(tau_fast) + w FO(tau_slow)``."""
    return (1.0 - p.w_slow) * first_order_lag(f, p.tau_fast, db) \
        + p.w_slow * first_order_lag(f, p.tau_slow, db)


def delivered_flow(
    tg: NDArray,
    In_grid: NDArray,
    P_grid: NDArray,
    p: DeliveryParams,
    db: float,
    *,
    taud_of_Q: bool = False,
) -> tuple[NDArray, NDArray]:
    """Delivered flow of each pump on the uniform grid ``tg``.

    Parameters
    ----------
    tg : ndarray
        Uniform time grid [s] (spacing ``db``).
    In_grid, P_grid : ndarray
        Commanded In/P flows interpolated onto ``tg`` [uL/min].
    p : DeliveryParams
        Validated delivery parameters.
    db : float
        Grid spacing [s].
    taud_of_Q : bool, optional
        If True, use the alternative flow-dependent lag ``tau_d(Q)=0.65+3.513e-4 Q``
        in place of the parallel fast/slow split.

    Returns
    -------
    (In_del, P_del) : tuple of ndarray
        Delivered In and P flows on ``tg`` [uL/min].
    """
    gI = p.g0 * g_bp(In_grid, p.beta)
    gP = p.aP * g_bp(P_grid, p.beta)
    fIn = deadtime(gI * In_grid, tg, p.theta_In)
    fP = deadtime(gP * P_grid, tg, p.theta_P)
    if taud_of_Q:
        tau_tot = 0.65 + 3.513e-4 * (In_grid + P_grid)
        return varying_lag(fIn, tau_tot, db), varying_lag(fP, tau_tot, db)
    return two_lag(fIn, p, db), two_lag(fP, p, db)


def delivered_flow_pump(tg: NDArray, u_grid: NDArray, pump: PumpDelivery, db: float,
                        *, taud_of_Q: bool = False) -> NDArray:
    """Delivered flow of ONE pump from its command on grid ``tg`` [uL/min].

    Identical pipeline to :func:`delivered_flow` per stream: gain*backpressure ->
    dead time -> parallel fast/slow lag. ``PumpDelivery`` exposes the same
    ``tau_fast/w_slow/tau_slow`` fields that :func:`two_lag` reads.
    """
    g = pump.gain * g_bp(u_grid, pump.beta)
    f = deadtime(g * u_grid, tg, pump.theta)
    if taud_of_Q:
        return varying_lag(f, 0.65 + 3.513e-4 * u_grid, db)
    return two_lag(f, pump, db)


def delivered_flows(tg: NDArray, cmd_grids: Mapping[str, NDArray],
                    pumps: Sequence[PumpDelivery], db: float,
                    *, taud_of_Q: bool = False) -> dict[str, NDArray]:
    """Delivered flow per pump (n-pump generalization of :func:`delivered_flow`).

    Parameters
    ----------
    tg : ndarray
        Uniform time grid [s].
    cmd_grids : mapping
        ``pump.name -> commanded flow on tg`` [uL/min].
    pumps : sequence of PumpDelivery
        The pumps to deliver.
    db : float
        Grid spacing [s].

    Returns
    -------
    dict
        ``pump.name -> delivered flow on tg`` [uL/min]. With pumps ``[In, P]`` whose
        params match ``DeliveryParams``, this reproduces :func:`delivered_flow` exactly.
    """
    return {p.name: delivered_flow_pump(tg, cmd_grids[p.name], p, db, taud_of_Q=taud_of_Q)
            for p in pumps}
