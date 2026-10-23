"""Provenance-tagged values: every number in the Standard says where it came from (SCOPE.md §4)."""
from __future__ import annotations

from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

Provenance = Literal[
    "paper_stated",  # given in the paper or its supplementary information
    "inferred",      # filled in by the LLM or a person, with reasoning in `note`
    "measured",      # recorded during our physical run
    "calibrated",    # fitted by the digital twin against our data
    "assumed",       # a default we chose, flagged so others can revisit it
    "missing",       # not known; `value` is None
]

T = TypeVar("T")


class Tagged(BaseModel, Generic[T]):
    """A value plus where it came from. An absent value is always `provenance="missing"`."""

    model_config = ConfigDict(extra="forbid")

    value: Optional[T] = None
    provenance: Provenance = "missing"
    source: Optional[str] = None  # quote + section/page, datasheet, instrument log, ...
    note: Optional[str] = None    # reasoning for inferred / assumed values

    @model_validator(mode="after")
    def _missing_iff_none(self):
        if (self.value is None) != (self.provenance == "missing"):
            raise ValueError("value must be None exactly when provenance is 'missing'")
        return self

    @property
    def known(self) -> bool:
        return self.value is not None


def stated(value, source: str | None = None) -> Tagged:
    return Tagged(value=value, provenance="paper_stated", source=source)


def missing(note: str | None = None) -> Tagged:
    return Tagged(note=note)
