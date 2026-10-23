"""Minimal unit handling for comparing claims. Extend the table as target papers need it."""
from __future__ import annotations

# unit -> (dimension, factor to the dimension's base unit)
_UNITS: dict[str, tuple[str, float]] = {
    "s": ("time", 1.0), "sec": ("time", 1.0), "min": ("time", 60.0), "h": ("time", 3600.0),
    "%": ("fraction", 0.01), "fraction": ("fraction", 1.0),
    "ul/min": ("flow", 1.0), "ml/min": ("flow", 1000.0),
    "ul": ("volume", 1.0), "ml": ("volume", 1000.0),
    # "M"/"mM" are left out on purpose: lowercased they collide with metres/millimetres.
    "mol/l": ("concentration", 1.0), "mmol/l": ("concentration", 1e-3),
    "c": ("temperature_c", 1.0), "degc": ("temperature_c", 1.0),
}


def _key(unit: str | None) -> str:
    return (unit or "").strip().lower().replace("µ", "u").replace("μ", "u").replace("°", "deg")


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Convert between compatible units; None if either is unknown or the dimensions differ."""
    if _key(from_unit) == _key(to_unit):
        return value
    a, b = _UNITS.get(_key(from_unit)), _UNITS.get(_key(to_unit))
    if a is None or b is None or a[0] != b[0]:
        return None
    return value * a[1] / b[1]
