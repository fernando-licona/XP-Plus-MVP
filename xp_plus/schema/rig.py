"""The shared rig description: one source of truth for both the twin and the physical build.

Units are fixed by field name (mm, uL, uL/min, degC, bar, nm) so no value needs a unit string.
Connection tubing lives on `Connection`: it is exactly the kind of metadata papers leave out.
"""
from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Tagged

ComponentKind = Literal[
    "reservoir", "pump", "mixer", "tubing", "reactor", "detector", "collection",
    "valve", "back_pressure_regulator", "other",
]

TaggedFloat = Tagged[float]
TaggedStr = Tagged[str]


def _f():
    return Field(default_factory=TaggedFloat)


def _s():
    return Field(default_factory=TaggedStr)


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ComponentKind
    name: Optional[str] = None

    manufacturer: TaggedStr = _s()
    model: TaggedStr = _s()
    material: TaggedStr = _s()

    inner_diameter_mm: TaggedFloat = _f()
    length_mm: TaggedFloat = _f()
    volume_uL: TaggedFloat = _f()
    flow_rate_uL_min: TaggedFloat = _f()
    temperature_C: TaggedFloat = _f()
    pressure_bar: TaggedFloat = _f()
    path_length_mm: TaggedFloat = _f()
    wavelength_nm: TaggedFloat = _f()

    # reservoir contents: species name -> concentration [mol/L]
    contents: dict[str, TaggedFloat] = Field(default_factory=dict)

    def tube_volume_uL(self) -> Optional[float]:
        """Volume from inner diameter and length (mm^3 == uL), if both are known."""
        if self.inner_diameter_mm.known and self.length_mm.known:
            return math.pi * (self.inner_diameter_mm.value / 2) ** 2 * self.length_mm.value
        return None

    def volume_estimate_uL(self) -> Optional[float]:
        """Stated volume, else the tube volume."""
        return self.volume_uL.value if self.volume_uL.known else self.tube_volume_uL()


class Connection(BaseModel):
    """Fluid path from `src` to `dst`, with the tubing between them."""

    model_config = ConfigDict(extra="forbid")

    src: str
    dst: str
    direct: bool = False  # no tubing (e.g. a syringe mounted on its pump, fittings butted together)
    inner_diameter_mm: TaggedFloat = _f()
    length_mm: TaggedFloat = _f()
    material: TaggedStr = _s()

    @property
    def key(self) -> str:
        return f"{self.src}->{self.dst}"


class Rig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: list[Component] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)

    def component(self, component_id: str) -> Component:
        for c in self.components:
            if c.id == component_id:
                return c
        raise KeyError(component_id)

    def of_kind(self, *kinds: str) -> list[Component]:
        return [c for c in self.components if c.kind in kinds]

    def downstream(self, component_id: str) -> list[str]:
        return [e.dst for e in self.connections if e.src == component_id]

    def upstream(self, component_id: str) -> list[str]:
        return [e.src for e in self.connections if e.dst == component_id]
