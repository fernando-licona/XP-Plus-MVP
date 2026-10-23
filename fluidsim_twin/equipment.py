"""Equipment library/database: idealized MODELS + calibrated UNITS (DESIGN.md §7.3).

Two layers, both stored as editable TOML in ``data/``:

* **Models** (``equipment_models.toml``) — manufacturer-nominal parameters for a make/model
  (how a brand-new unit should behave, from vendor docs). The default for new equipment.
* **Units** (``equipment_units.toml``) — specific physical pieces keyed by serial number, with
  a nickname and the *measured* calibration that overrides the model. The growing database of
  "serial #### behaves like X", tracked by type → manufacturer → model → serial → nickname.

The library is **general** (every record carries a ``type``: "pump", "temperature_controller",
…) so new equipment kinds slot in without code changes. The only type-specific helper today is
:func:`resolve_pump_delivery`, which turns a chosen pump model (+ optional calibrated unit) into
an m6flow :class:`~m6flow.params.PumpDelivery`. Composition (what a pump carries) is NOT part of
the model/unit — it is a run/feed property set by a reservoir, a source tag, or the reaction
library.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from m6flow.params import PumpDelivery

_DATA = Path(__file__).with_name("data")
_MODELS_PATH = _DATA / "equipment_models.toml"
_UNITS_PATH = _DATA / "equipment_units.toml"

# DC-FOPDT fields an entry may set (everything else in an entry is metadata).
_PUMP_DELIVERY_FIELDS = ("gain", "beta", "theta", "tau_fast", "w_slow", "tau_slow", "rho",
                         "calibrated")

# Reactor module config fields (a [[reactor]] entry may set these; A_c/L are derived from R/V_R).
_REACTOR_FIELDS = ("V_R", "R", "rtd_model", "rtd_params", "temperature_K", "shape",
                   "reactor_material", "tube_material")

# Flow-cell config fields (a [[flow_cell]] entry may set these). The cell is the instrument node's
# hardware: an optical path length (Beer-Lambert) + a holdup volume (transport lag).
_FLOW_CELL_FIELDS = ("path_length_mm", "cell_volume_uL", "rtd_model", "rtd_params",
                     "cell_material", "window_material")


@dataclass(frozen=True)
class EquipmentModel:
    """A make/model's idealized parameters + descriptive metadata."""

    type: str
    manufacturer: str
    model: str
    params: dict = field(default_factory=dict)        # nominal parameters (type-specific)

    @property
    def label(self) -> str:
        return f"{self.manufacturer} {self.model}"


@dataclass(frozen=True)
class EquipmentUnit:
    """One physical unit: serial + nickname + measured calibration overriding its model."""

    type: str
    manufacturer: str
    model: str
    serial: str
    nickname: str = ""
    calibration: dict = field(default_factory=dict)   # measured overrides + metadata

    @property
    def label(self) -> str:
        tag = self.nickname or self.serial
        return f"{tag} ({self.serial})" if self.nickname else self.serial


def _load(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def load_models(path: str | Path | None = None) -> list[EquipmentModel]:
    """Load the idealized-model library (every ``[[type]]`` section across the file)."""
    doc = _load(Path(path) if path else _MODELS_PATH)
    out = []
    for etype, entries in doc.items():
        for e in entries:
            params = {k: v for k, v in e.items() if k not in ("manufacturer", "model")}
            out.append(EquipmentModel(type=etype, manufacturer=e["manufacturer"],
                                      model=e["model"], params=params))
    return out


def load_units(path: str | Path | None = None) -> list[EquipmentUnit]:
    """Load the unit/calibration registry."""
    doc = _load(Path(path) if path else _UNITS_PATH)
    out = []
    for etype, entries in doc.items():
        for e in entries:
            cal = {k: v for k, v in e.items()
                   if k not in ("manufacturer", "model", "serial", "nickname")}
            out.append(EquipmentUnit(type=etype, manufacturer=e["manufacturer"],
                                     model=e["model"], serial=e["serial"],
                                     nickname=e.get("nickname", ""), calibration=cal))
    return out


def find_model(etype: str, manufacturer: str, model: str,
               models: list[EquipmentModel] | None = None) -> EquipmentModel | None:
    for m in (models if models is not None else load_models()):
        if m.type == etype and m.manufacturer == manufacturer and m.model == model:
            return m
    return None


def find_unit(serial: str, units: list[EquipmentUnit] | None = None) -> EquipmentUnit | None:
    for u in (units if units is not None else load_units()):
        if u.serial == serial:
            return u
    return None


def model_by_label(label: str | None, etype: str | None = None,
                   models: list[EquipmentModel] | None = None) -> EquipmentModel | None:
    """Find a model by its ``"Manufacturer Model"`` label (optionally restricted to a type)."""
    if not label:
        return None
    for m in (models if models is not None else load_models()):
        if m.label == label and (etype is None or m.type == etype):
            return m
    return None


def pump_models() -> list[EquipmentModel]:
    return [m for m in load_models() if m.type == "pump"]


def pump_units(manufacturer: str | None = None, model: str | None = None) -> list[EquipmentUnit]:
    out = [u for u in load_units() if u.type == "pump"]
    if manufacturer:
        out = [u for u in out if u.manufacturer == manufacturer]
    if model:
        out = [u for u in out if u.model == model]
    return out


def reactor_models() -> list[EquipmentModel]:
    return [m for m in load_models() if m.type == "reactor"]


def reactor_units(manufacturer: str | None = None, model: str | None = None) -> list[EquipmentUnit]:
    out = [u for u in load_units() if u.type == "reactor"]
    if manufacturer:
        out = [u for u in out if u.manufacturer == manufacturer]
    if model:
        out = [u for u in out if u.model == model]
    return out


def resolve_reactor_config(*, manufacturer: str | None = None, model: str | None = None,
                           serial: str | None = None) -> dict:
    """Resolve a reactor module to a flat config dict (the GUI/build read these).

    Starts from the idealized model's params; if ``serial`` names a unit, that unit's measured
    calibration (e.g. a fitted ``rtd_model``/``rtd_params``) overrides them. ``A_c = pi*R^2`` and
    ``L = V_R/A_c`` are derived so the single volume ``V_R`` stays the source of truth.
    """
    m = find_model("reactor", manufacturer, model) if (manufacturer and model) else None
    p = dict(m.params) if m else {}
    if serial:
        u = find_unit(serial)
        if u:
            p.update(u.calibration)
    R = float(p.get("R", 0.381))
    V_R = float(p.get("V_R", 1000.0))
    A_c = math.pi * R * R
    L = V_R / A_c if A_c > 0 else 0.0
    return {
        "R": R, "A_c": A_c, "L": L, "V_R": V_R,
        "rtd_model": p.get("rtd_model", "plug"),
        "rtd_params": list(p.get("rtd_params", [])),
        "temperature_K": float(p.get("temperature_K", 298.15)),
        "shape": p.get("shape", "serpentine"),
        "reactor_material": p.get("reactor_material", "aluminum"),
        "tube_material": p.get("tube_material", "PFA"),
    }


def flow_cell_models() -> list[EquipmentModel]:
    return [m for m in load_models() if m.type == "flow_cell"]


def flow_cell_units(manufacturer: str | None = None, model: str | None = None) -> list[EquipmentUnit]:
    out = [u for u in load_units() if u.type == "flow_cell"]
    if manufacturer:
        out = [u for u in out if u.manufacturer == manufacturer]
    if model:
        out = [u for u in out if u.model == model]
    return out


def spectrometer_models() -> list[EquipmentModel]:
    return [m for m in load_models() if m.type == "spectrometer"]


def light_source_models() -> list[EquipmentModel]:
    return [m for m in load_models() if m.type == "light_source"]


def resolve_flow_cell_config(*, manufacturer: str | None = None, model: str | None = None,
                             serial: str | None = None) -> dict:
    """Resolve a flow-cell model (+ optional calibrated unit) to a flat config dict.

    Starts from the idealized model's params; a named ``serial`` unit's measured calibration
    (true path length / holdup) overrides them. The instrument node reads ``cell_volume_uL`` as
    its holdup ``V`` and ``path_length_mm`` for the Beer-Lambert path (UV-4)."""
    m = find_model("flow_cell", manufacturer, model) if (manufacturer and model) else None
    p = dict(m.params) if m else {}
    if serial:
        u = find_unit(serial)
        if u:
            p.update(u.calibration)
    return {
        "path_length_mm": float(p.get("path_length_mm", 10.0)),
        "cell_volume_uL": float(p.get("cell_volume_uL", 30.0)),
        "rtd_model": p.get("rtd_model", "plug"),
        "rtd_params": list(p.get("rtd_params", [])),
        "cell_material": p.get("cell_material", ""),
        "window_material": p.get("window_material", ""),
    }


def resolve_pump_delivery(*, manufacturer: str | None = None, model: str | None = None,
                          serial: str | None = None, name: str | None = None,
                          composition: dict | None = None,
                          carries_dye: bool = False, c_value: float = 0.0) -> PumpDelivery:
    """Build an m6flow ``PumpDelivery`` from a pump model (+ optional calibrated unit).

    Starts from the idealized model's nominal DC-FOPDT params; if ``serial`` names a unit in
    the registry, that unit's measured calibration overrides them. ``composition``/``carries_dye``
    /``c_value`` are run/feed properties (not stored on the model/unit) and pass straight through.
    """
    manufacturer = manufacturer or "VICI"
    model = model or "M6"
    m = find_model("pump", manufacturer, model)
    p = dict(m.params) if m else {}
    if serial:
        u = find_unit(serial)
        if u:
            p.update(u.calibration)
    fields = {k: p[k] for k in _PUMP_DELIVERY_FIELDS if k in p}
    return PumpDelivery(name=name or serial or model,
                        composition=composition, carries_dye=carries_dye, C_value=c_value,
                        **fields)
