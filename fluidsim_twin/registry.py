"""Sub-type + tubing registries: UX presets that resolve to m6flow params (DESIGN.md §7.3).

These are *not* new physics — they prefill m6flow's ``PumpDelivery`` / ``Geometry`` from
friendly choices (pump sub-type, tubing bore + length). m6flow's node types are unchanged.
"""
from __future__ import annotations

import math
from dataclasses import replace

from m6flow.params import PUMP_IN, PUMP_M50, PUMP_P, Geometry, PumpDelivery

# Pump sub-type presets -> the validated m6flow PumpDelivery constants.
PUMP_PRESETS: dict[str, PumpDelivery] = {
    "VICI_M6_In": PUMP_IN,     # dye-carrying inlet pump
    "VICI_M6_P": PUMP_P,       # diluent inlet pump
    "VICI_M50": PUMP_M50,      # high-pressure reference pump (uncalibrated)
}

# Named tubing presets: inner diameter [mm]. The validated reactor bore is 0.030" ID.
TUBING_ID_MM: dict[str, float] = {
    "PFA_0.030in": 0.762,      # R = 0.381 mm -> matches m6flow REACTOR_GEOMETRY bore
}


def geometry_from_tubing(id_mm: float, length_mm: float, *, material: str | None = None) -> Geometry:
    """Compute an m6flow ``Geometry`` from tube inner diameter + length.

    ``R = id/2``; ``A_c = pi R^2`` [mm^2 = uL/mm]; ``V_R = A_c * L`` [uL]. ``material`` is
    carried for display/future dispersion use and does not affect the geometry.
    """
    R = 0.5 * float(id_mm)
    A_c = math.pi * R * R
    L = float(length_mm)
    return Geometry(R=R, A_c=A_c, L=L, V_R=A_c * L)


def pump_from_spec(preset: str | None = None, overrides: dict | None = None,
                   *, name: str | None = None, manufacturer: str | None = None,
                   model: str | None = None, serial: str | None = None) -> PumpDelivery:
    """Build a ``PumpDelivery`` from a pump selection plus optional field overrides.

    Resolution order:
    * **manufacturer/model/serial** (preferred) -> the equipment library: idealized model +
      optional per-serial calibration (see :func:`fluidsim_twin.equipment.resolve_pump_delivery`);
    * **preset** (legacy) -> the validated registry constants, byte-identical to before;
    * otherwise a generic M6-like pump.
    ``overrides`` is a mapping of ``PumpDelivery`` field names to values (e.g.
    ``{"carries_dye": True, "C_value": 1.0}``) applied last so explicit values always win.
    """
    ov = {k: v for k, v in (overrides or {}).items() if v is not None}
    if manufacturer or model or serial:
        from .equipment import resolve_pump_delivery
        base = resolve_pump_delivery(
            manufacturer=manufacturer, model=model, serial=serial, name=name,
            composition=ov.pop("composition", None),
            carries_dye=bool(ov.pop("carries_dye", False)),
            c_value=float(ov.pop("C_value", 0.0)))
    else:
        if preset is not None and preset not in PUMP_PRESETS:
            raise KeyError(f"unknown pump preset {preset!r}; known: {sorted(PUMP_PRESETS)}")
        base = PUMP_PRESETS[preset] if preset else PumpDelivery(name=name or "pump")
    if name is not None and base.name != name and "name" not in ov:
        ov["name"] = name
    return replace(base, **ov) if ov else base
