"""Observation primitives shared by the two branches: mass and the optical inlet.

Implements the conversions of ``two_pump_model.tex`` Chapters "The Validated
Delivery Model" (cumulative mass) and "Optical Branch: Beer-Lambert Observation".
All quantities are in **seconds** / **grams** / ``uL/min``; the ``rho/60`` factor
converts an ``uL/min`` flow integrated over seconds into grams.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import cumulative_trapezoid

from ..units import SEC_PER_MIN


def mass_rate(Q_uL_min: NDArray, rho: float) -> NDArray:
    """Mass delivery rate ``dM/dt = rho Q / 60`` [g/s] from total flow ``Q`` [uL/min]."""
    return np.asarray(Q_uL_min, float) * rho / SEC_PER_MIN


def cumulative_mass(Q_uL_min: NDArray, tg: NDArray, rho: float) -> NDArray:
    """Cumulative delivered mass ``M(t) = (rho/60) integral(Q dt)`` [g] on grid ``tg`` [s]."""
    rate = mass_rate(Q_uL_min, rho)
    return cumulative_trapezoid(rate, tg, initial=0.0)


def inlet_fraction(In_del: NDArray, P_del: NDArray, eps: float = 1e-6) -> NDArray:
    """Inlet In-stream (dye) fraction ``f_in = In_del / (In_del + P_del)``.

    Zero where the total delivered flow is below ``eps`` (no fluid -> no dye signal).
    """
    total = np.asarray(In_del, float) + np.asarray(P_del, float)
    return np.where(total > eps, In_del / np.where(total > eps, total, 1.0), 0.0)


def beer_lambert(r_cell: NDArray, A_full: float, offset: float) -> NDArray:
    """Beer-Lambert absorbance ``A = A_full * r_cell + offset`` (linear, q = 1)."""
    return A_full * np.asarray(r_cell, float) + offset
