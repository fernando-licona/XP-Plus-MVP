"""Gaps: values the procedure needs that the paper does not give, and how each was closed."""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Provenance

GapSource = Literal[
    "extraction",        # the LLM / annotator noticed it
    "gate_structural",   # the twin cannot be connected end to end
    "gate_parametric",   # the solver is missing a value it needs
    "gate_consistency",  # values contradict each other
    "gate_model",        # a paper's data-driven model cannot be rebuilt as described
    "comparison",        # surfaced by a disagreement between paper, twin and physical
]


class Resolution(BaseModel):
    """A value that closes a gap.

    `target` is a path into PaperFeatures, e.g.
        rig.components.coil.inner_diameter_mm
        rig.connections.coil->cell.length_mm
        chemistry.reagents.dye.concentration_M
        environment.relative_humidity_pct
    """

    model_config = ConfigDict(extra="forbid")

    target: str
    value: Union[float, str]
    provenance: Provenance  # must not be "missing"
    source: Optional[str] = None
    note: Optional[str] = None


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    # Same path syntax as Resolution.target. May be a prefix (rig.connections.a->b) that
    # several resolutions fall under (its inner_diameter_mm and length_mm).
    target: str
    description: str
    detected_by: GapSource
    blocking: bool = True  # True: the twin cannot run until it is closed
    status: Literal["open", "resolved"] = "open"
    resolutions: list[Resolution] = Field(default_factory=list)
    impact: Optional[str] = None  # measured / simulated effect on the result (sensitivity, TODO)
    closure_reason: Optional[str] = None  # explicit reviewed reason, distinct from scientific impact
