from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..schema import Gap, PaperFeatures


class Extraction(BaseModel):
    """Extractor output. Every value in `features` carries provenance; `gaps` lists what's absent."""

    model_config = ConfigDict(extra="forbid")

    features: PaperFeatures
    gaps: list[Gap] = Field(default_factory=list)


class Extractor(Protocol):
    def extract(self, source: str | Path) -> Extraction: ...
