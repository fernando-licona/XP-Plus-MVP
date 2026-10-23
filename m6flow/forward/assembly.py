"""Assembled forward maps: pump commands -> (balance reading, absorbance).

Implements ``two_pump_model.tex`` Chapter "Synthesis: the Complete Forward Map":
the shared delivery core drives both observation branches. This module composes the
delivery, balance, observation, and TV-RTD pieces into end-to-end maps.

:func:`forward_reading` reproduces ``previous-work/toolset.forward_reading`` exactly
(the validated cumulative-mass forward model). The optical map
:func:`forward_absorbance` is added with the TV-RTD branch.

All time quantities here are in **seconds**.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..params import BalanceConst, DeliveryParams, DEFAULT_BALANCE, DEFAULT_DELIVERY
from . import balance as _balance
from . import delivery as _delivery
from . import observation as _obs


@dataclass
class ForwardReading:
    """Result of the gravimetric forward map."""

    r: NDArray            # predicted reading on the input grid ``t`` [g]
    tg: NDArray           # internal uniform grid [s]
    Q: NDArray            # total delivered flow on ``tg`` [uL/min]
    In_del: NDArray       # delivered In flow on ``tg`` [uL/min]
    P_del: NDArray        # delivered P flow on ``tg`` [uL/min]


def forward_reading(
    t: NDArray,
    In: NDArray,
    P: NDArray,
    *,
    p: DeliveryParams = DEFAULT_DELIVERY,
    balance: BalanceConst = DEFAULT_BALANCE,
    b0: float = 0.0,
    taud_of_Q: bool = False,
    latch: bool = False,
    quantise: bool = False,
) -> ForwardReading:
    """Predict the balance reading ``r(t)`` from In/P commands [uL/min].

    Mirrors the validated ``toolset.forward_reading``: interpolate commands onto the
    uniform latch grid, compute delivered flows (gain, dead time, fast/slow lag),
    convert to a mass rate, pass through the balance operator, and interpolate back
    to the input times. ``latch``/``quantise`` default off to match the validated
    continuous-smoothing cumulative-mass fit.
    """
    t = np.asarray(t, float)
    tg = np.arange(t[0], t[-1], balance.db)
    Ig = np.interp(tg, t, In)
    Pg = np.interp(tg, t, P)
    In_del, P_del = _delivery.delivered_flow(tg, Ig, Pg, p, balance.db, taud_of_Q=taud_of_Q)
    Q = In_del + P_del
    rate = _obs.mass_rate(Q, p.rho)
    y = _balance.reading_from_mass_rate(rate, tg, balance, b0=0.0, latch=latch, quantise=quantise)
    r = np.interp(t, tg, y) + b0
    return ForwardReading(r=r, tg=tg, Q=Q, In_del=In_del, P_del=P_del)
