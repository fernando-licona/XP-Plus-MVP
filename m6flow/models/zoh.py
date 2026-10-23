"""Unified analytical zero-order-hold (ZOH) solvers for the lumped delivery models.

Between consecutive (dead-time-shifted) input breakpoints the delayed command is
constant, so each first-order lag has the exact solution

    phi(t) = phi(t_k) exp(-(t-t_k)/tau) + a u_k (1 - exp(-(t-t_k)/tau)).

:func:`zoh_phi` is the single-pole (FOPDT) propagator (ported verbatim from
``previous-work/.../zoh_solver.zoh_phi_fast``); the second-order (SOPDT, cascaded)
and merged downstream-compliance (DC) branches build on the same per-segment
propagation and are added with their model plugins.

All in **seconds** / ``uL/min``; this replaces ``scipy.odeint`` with an O(n_breaks)
inner loop plus a vectorised O(n_output) evaluation (100-1400x faster).
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def zoh_phi(t_array: NDArray, a: float, tau: float, theta: float,
            u_t_breaks: NDArray, u_vals: NDArray, phi0: float = 0.0) -> NDArray:
    """Analytical ``phi(t)`` for a single first-order lag under a ZOH command.

    Parameters
    ----------
    t_array : ndarray
        Strictly increasing output times [s].
    a, tau, theta : float
        Gain, time constant [s] (clamped >= 1e-9), and dead time [s].
    u_t_breaks, u_vals : ndarray
        ZOH breakpoint times [s] and the setpoint active from each (before the
        dead-time shift).
    phi0 : float
        Initial state at ``t_array[0]``.
    """
    tau = max(float(tau), 1e-9)
    t0 = float(t_array[0])

    sb = u_t_breaks + theta
    mask = sb >= t0
    sb_in = sb[mask]
    uv_in = u_vals[mask]
    if len(sb_in) == 0 or sb_in[0] > t0:
        idx0 = int(np.searchsorted(u_t_breaks, t0 - theta, side="right")) - 1
        idx0 = int(np.clip(idx0, 0, len(u_vals) - 1))
        sb_in = np.concatenate([[t0], sb_in])
        uv_in = np.concatenate([[u_vals[idx0]], uv_in])

    n_piv = len(sb_in)
    phi_piv = np.empty(n_piv)
    phi_piv[0] = phi0
    for k in range(n_piv - 1):
        e = np.exp(-(sb_in[k + 1] - sb_in[k]) / tau)
        phi_piv[k + 1] = phi_piv[k] * e + a * uv_in[k] * (1.0 - e)

    si = np.clip(np.searchsorted(sb_in, t_array, side="right") - 1, 0, n_piv - 1)
    dt_vec = t_array - sb_in[si]
    exp_vec = np.exp(-dt_vec / tau)
    return phi_piv[si] * exp_vec + a * uv_in[si] * (1.0 - exp_vec)


def phi_cascade(t_array: NDArray, a: float, tau1: float, tau2: float, theta: float,
                u_t_breaks: NDArray, u_vals: NDArray, phi0: tuple[float, float] = (0.0, 0.0)) -> NDArray:
    """Two first-order lags in series (SOPDT) by chaining :func:`zoh_phi`.

    Stage 1 is a unit-gain lag of the (gained, delayed) command; stage 2 lags stage
    1's output. The output is re-gridded to a fine ZOH so stage 2 sees a
    piecewise-constant input. Exact in the ``tau1, tau2`` limits; adequate elsewhere.
    """
    stage1 = zoh_phi(t_array, a, tau1, theta, u_t_breaks, u_vals, phi0[0])
    # feed stage1 as a dense ZOH command into a unit-gain lag tau2 (no extra delay)
    return zoh_phi(t_array, 1.0, tau2, 0.0, t_array, stage1, phi0[1])
