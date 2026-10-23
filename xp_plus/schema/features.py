"""What the paper describes, broken into structured features (SCOPE.md §3.1)."""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .model import ModelCard
from .rig import Rig, TaggedFloat, TaggedStr


class PaperRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    doi: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None


class Reagent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: Optional[str] = None  # reactant, catalyst, solvent, tracer, ...
    concentration_M: TaggedFloat = Field(default_factory=TaggedFloat)
    supplier: TaggedStr = Field(default_factory=TaggedStr)
    purity: TaggedStr = Field(default_factory=TaggedStr)
    lot: TaggedStr = Field(default_factory=TaggedStr)


class Chemistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reagents: list[Reagent] = Field(default_factory=list)
    solvent: TaggedStr = Field(default_factory=TaggedStr)


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambient_temperature_C: TaggedFloat = Field(default_factory=TaggedFloat)
    relative_humidity_pct: TaggedFloat = Field(default_factory=TaggedFloat)
    ambient_pressure_kPa: TaggedFloat = Field(default_factory=TaggedFloat)
    other: dict[str, TaggedStr] = Field(default_factory=dict)


class ProtocolStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    action: str  # set_flow_rate, set_temperature, wait, sample, flush, ...
    component: Optional[str] = None  # rig component id this step acts on
    parameters: dict[str, TaggedFloat] = Field(default_factory=dict)
    duration_s: TaggedFloat = Field(default_factory=TaggedFloat)


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    instrument: str  # rig component id (a detector)
    observable: str  # absorbance, f_curve, conversion, yield, ...
    species: Optional[str] = None
    wavelength_nm: TaggedFloat = Field(default_factory=TaggedFloat)
    processing: TaggedStr = Field(default_factory=TaggedStr)  # how the number is computed
    t0_step: Optional[str] = None  # protocol step id that defines t = 0 (e.g. the tracer step)


class Claim(BaseModel):
    """A figure of merit the paper says it achieved."""

    model_config = ConfigDict(extra="forbid")

    id: str
    metric: str  # yield, conversion, residence_time, ...
    value: Union[float, str]
    unit: Optional[str] = None
    qualifier: Literal["=", "~", ">", "<"] = "="
    # Absolute agreement tolerance in `unit` (match <= tol, partial <= 2.5 tol). When unset, the
    # relative 10% / 25% rules apply, which are meaningless for e.g. wavelengths.
    tolerance: Optional[float] = None
    tolerance_basis: Optional[str] = None  # why this tolerance (e.g. the paper's replicate SD)
    conditions: Optional[str] = None
    # Where along a simulated trajectory the claim applies, as model-input values in their
    # model units, e.g. {"tau": 3.0}: the steady-state equivalent condition of a DFE point.
    at: dict[str, float] = Field(default_factory=dict)
    source: Optional[str] = None


class PaperFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: PaperRef
    experiment: Optional[str] = None  # which experiment in the paper, e.g. "SI §1 RTD, tau = 9 min"
    rig: Rig = Field(default_factory=Rig)
    chemistry: Chemistry = Field(default_factory=Chemistry)
    environment: Environment = Field(default_factory=Environment)
    protocol: list[ProtocolStep] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    models: list[ModelCard] = Field(default_factory=list)  # data-driven models the paper builds
    claims: list[Claim] = Field(default_factory=list)


__all__ = [
    "Chemistry", "Claim", "Environment", "Measurement", "PaperFeatures", "PaperRef",
    "ProtocolStep", "Reagent",
]
