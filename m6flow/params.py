"""Validated physical constants and parameter containers.

These are the carried-forward best-fit values of the two-pump VICI M6 forward
model, identical to the values stated in ``two_pump_model.tex`` and the
``previous-work`` snapshot. Grouping them into frozen dataclasses (rather than loose
module globals) makes the provenance explicit and lets callers pass a coherent
parameter set around without ambiguity.

Unit convention (see :mod:`m6flow.units`):
    * balance / delivery quantities are in **seconds**, flows in ``uL/min``;
    * geometry is in ``mm`` / ``mm^2`` / ``uL``;
    * the TV-RTD layer reinterprets times in **minutes**.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceConst:
    """Balance measurement-operator constants (``two_pump_model.tex`` Ch. balance).

    Attributes
    ----------
    W_b : float
        Boxcar / moving-average width [s].
    tau_b : float
        First-order lag time constant [s].
    f_ref : float
        Zero-order-hold latch (sample-and-hold) rate [Hz].
    q : float
        Readout quantum [g] (0.1 mg).
    """

    W_b: float = 1.935
    tau_b: float = 0.273
    f_ref: float = 6.31
    q: float = 1e-4

    @property
    def db(self) -> float:
        """Latch interval ``1 / f_ref`` [s] (~0.1585 s)."""
        return 1.0 / self.f_ref

    @property
    def gd(self) -> float:
        """Group delay ``tau_b + W_b / 2`` [s] (~1.2405 s)."""
        return self.tau_b + self.W_b / 2.0


@dataclass(frozen=True)
class Geometry:
    """Reactor / tubing geometry (``two_pump_model.tex`` Ch. four models).

    ``A_c`` in ``mm^2`` is numerically equal to ``uL/mm``; ``V_R = A_c * L``.
    """

    R: float = 0.381       # tube inner radius [mm]
    A_c: float = 0.456     # cross-sectional area [mm^2] (= uL/mm)
    L: float = 4715.0      # effective reactor length [mm]
    V_R: float = 2150.0    # reactor / system volume [uL]


@dataclass(frozen=True)
class DeliveryParams:
    """DC-FOPDT delivery-model parameters (``two_pump_model.tex`` Ch. delivery).

    The per-pump delivered flow is
    ``L[ deadtime_theta_p( g_p(Q) * Q_cmd ) ]`` with gain
    ``g_In = g0 * g_bp(Q)``, ``g_P = aP * g_bp(Q)``, turbulent-backpressure gain
    ``g_bp``, and the parallel fast/slow lag
    ``(1 - w_slow) * FO(tau_fast) + w_slow * FO(tau_slow)``.
    """

    g0: float = 1.0112             # In-pump nominal gain
    beta: float = 8.912e-5         # turbulent-backpressure coefficient [min/uL]
    aP: float = 0.9787             # P-pump gain scale
    tau_fast: float = 1.072        # fast lag time constant [s]
    w_slow: float = 0.0081         # slow-mode weight
    tau_slow: float = 78.9         # slow lag time constant [s]
    theta_In: float = 0.40         # In-pump dead time [s]
    theta_P: float = 0.80          # P-pump dead time [s]
    rho: float = 7.89e-4           # fluid density [g/uL] (1-octadecene)


@dataclass(frozen=True)
class PumpDelivery:
    """One pump's delivery sub-model and the composition its stream carries.

    Generalizes the In/P split in :class:`DeliveryParams` to a single, named pump that
    can be wired anywhere in a flow graph (see :mod:`m6flow.network`). The delivered
    flow is ``L[ deadtime_theta( gain * g_bp(Q) * Q_cmd ) ]`` with the parallel
    fast/slow lag ``L``; ``C_value`` is the (dye) composition the stream carries.

    Attributes
    ----------
    name : str
        Pump / stream label ("In", "P", "M50").
    gain : float
        Steady gain scale (was ``g0`` for In, ``aP`` for P).
    beta : float
        Turbulent-backpressure coefficient [min/uL].
    theta : float
        Pure dead time [s].
    carries_dye : bool
        True if the stream carries tracer (In). The optical observation reads dye.
    C_value : float
        Composition (dye level) of this pump's stream: In = 1, P = 0, M50 reference = 0.
    rho : float
        Stream density [g/uL] (for the gravimetric branch).
    calibrated : bool
        False flags an assumed-from-specs sub-model (the M50) pending future data.
    """

    name: str
    gain: float = 1.0
    beta: float = 8.912e-5
    theta: float = 0.40
    tau_fast: float = 1.072
    w_slow: float = 0.0081
    tau_slow: float = 78.9
    rho: float = 7.89e-4
    carries_dye: bool = False
    C_value: float = 0.0
    calibrated: bool = True
    composition: dict | None = None     # species -> inlet concentration; None -> {"dye": C_value}

    def species_composition(self) -> dict:
        """The per-species inlet composition this stream carries.

        ``None`` (the validated single-tracer default) reproduces the scalar dye model
        exactly: ``{"dye": C_value}``. A reactive run supplies an explicit map, e.g.
        ``{"A": 1.0}`` for a stream feeding pure reactant A.
        """
        return dict(self.composition) if self.composition is not None else {"dye": self.C_value}


# Reactor-stage geometry (the 1677 uL tubular reactor of the 3-pump case study).
REACTOR_GEOMETRY = Geometry(R=0.381, A_c=0.456, L=3677.0, V_R=1677.0)

# The three pumps. In carries the Sudan-Blue dye; P is dye-free; M50 is the (assumed,
# uncalibrated) high-pressure reference-material stream injected post-reactor.
PUMP_IN = PumpDelivery("In", gain=1.0112, beta=8.912e-5, theta=0.40,
                       carries_dye=True, C_value=1.0)
PUMP_P = PumpDelivery("P", gain=0.9787, beta=8.912e-5, theta=0.80,
                      carries_dye=False, C_value=0.0)
PUMP_M50 = PumpDelivery("M50", gain=1.0, beta=8.912e-5, theta=0.80,
                        carries_dye=False, C_value=0.0, calibrated=False)

# Module-level singletons holding the validated defaults.
DEFAULT_BALANCE = BalanceConst()
DEFAULT_GEOMETRY = Geometry()
DEFAULT_DELIVERY = DeliveryParams()
