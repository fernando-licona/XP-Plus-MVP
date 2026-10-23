"""Unit-convention helpers --- the single seconds/minutes conversion boundary.

Implements the dual-unit convention documented in ``two_pump_model.tex``
(Chapter "Symbols, Units, and Conventions"):

* The **delivery** and **balance** layers (and all of estimation / reconstruction)
  work in **seconds**, with flows in microlitres-per-minute converted through the
  ``1/60`` factor wherever an integral over time appears.
* The **TV-RTD** layer (:mod:`m6flow.forward.tvrtd`) works in **minutes**: ages and
  times are in minutes and flow in microlitres-per-minute, so the dispersion
  groupings ``a = 2 A_c^2 Dbar11`` and ``b = R^2 / (24 D22)`` carry the
  diffusivities in ``mm^2/min``.

Every conversion between the two conventions routes through a named helper in this
module, so a reviewer can ``grep`` for ``units.`` to find every boundary crossing.
There should be no bare ``/ 60`` or ``* 60`` anywhere else in the package.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

#: Seconds per minute --- the only magic constant for the time-unit conversion.
SEC_PER_MIN: float = 60.0

#: Conversion factor from ``mm^2/min`` to ``cm^2/s`` (= 1/6000): ``1 cm^2/s`` is
#: ``100 mm^2/s`` is ``6000 mm^2/min``.
MM2MIN_PER_CM2S: float = 6000.0


def minutes(t_s: NDArray | float) -> NDArray | float:
    """Convert a time (or time array) from seconds to minutes."""
    return np.asarray(t_s, float) / SEC_PER_MIN if not np.isscalar(t_s) else t_s / SEC_PER_MIN


def seconds(t_min: NDArray | float) -> NDArray | float:
    """Convert a time (or time array) from minutes to seconds."""
    return np.asarray(t_min, float) * SEC_PER_MIN if not np.isscalar(t_min) else t_min * SEC_PER_MIN


def volume_uL_from_flow(Q_uL_min: NDArray | float, dt_s: float) -> NDArray | float:
    """Volume increment [uL] delivered over ``dt_s`` seconds at flow ``Q`` [uL/min].

    This is the ``rho``-free core of the cumulative-mass conversion
    ``M = (rho / 60) * integral(Q dt)``; see :func:`m6flow.forward.observation.cumulative_mass`.
    """
    return np.asarray(Q_uL_min, float) * dt_s / SEC_PER_MIN


def D_mm2min_to_cm2s(D_mm2min: float) -> float:
    """Convert a diffusivity from ``mm^2/min`` (TV-RTD internal) to ``cm^2/s``."""
    return D_mm2min / MM2MIN_PER_CM2S


def D_cm2s_to_mm2min(D_cm2s: float) -> float:
    """Convert a diffusivity from ``cm^2/s`` to ``mm^2/min`` (TV-RTD internal)."""
    return D_cm2s * MM2MIN_PER_CM2S
