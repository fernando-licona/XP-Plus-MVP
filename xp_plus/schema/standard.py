"""The Reproducibility Standard: the project's output file (SCOPE.md §3.5 and §4)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .features import PaperFeatures
from .gaps import Gap

STANDARD_VERSION = "0.1"

Verdict = Literal["match", "partial", "miss", "missing_data"]
OverallVerdict = Literal["reproduced", "partially_reproduced", "not_reproduced", "insufficient_data"]


class Quantity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    unit: Optional[str] = None
    std: Optional[float] = None  # predictive / measurement standard deviation, same unit


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str  # run_snapshot, command_transcript, raw_data, artifact, ...
    uri: str
    sha256: Optional[str] = None
    description: Optional[str] = None


class TwinRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str = "danamic-simulations/fluidsim_twin"
    fidelity: str
    assumptions: list[str] = Field(default_factory=list)  # modelling choices not from the paper
    calibrated_parameters: dict[str, float] = Field(default_factory=dict)
    predictions: dict[str, Quantity] = Field(default_factory=dict)


class PhysicalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runner: str  # flowlab, recorded, ...
    run_id: Optional[str] = None
    observations: dict[str, Quantity] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ComputationalRecord(BaseModel):
    """A rebuilt paper model and the metrics we got from re-running its validation."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    backend: str  # e.g. "botorch 0.x / gpytorch 1.x"
    training_data_sha256: Optional[str] = None
    n_training_points: int = 0
    metrics: dict[str, Quantity] = Field(default_factory=dict)  # keyed by claim metric
    assumptions: list[str] = Field(default_factory=list)


class ResultRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    metric: str
    unit: Optional[str] = None  # the paper's unit; twin/physical are converted into it
    paper: Union[float, str]
    twin: Optional[float] = None
    physical: Optional[float] = None
    computational: Optional[float] = None  # re-run of the paper's own model validation
    twin_verdict: Verdict = "missing_data"
    physical_verdict: Verdict = "missing_data"
    computational_verdict: Verdict = "missing_data"


class Iteration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    changes: list[str] = Field(default_factory=list)
    summary: str = ""


class ReproStandard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_version: str = STANDARD_VERSION
    standard_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reproduced_by: list[str] = Field(default_factory=list)

    # The full, resolved experiment description. Every value is provenance-tagged.
    features: PaperFeatures

    twin: Optional[TwinRecord] = None
    physical: Optional[PhysicalRecord] = None
    computational: list[ComputationalRecord] = Field(default_factory=list)
    results: list[ResultRow] = Field(default_factory=list)
    verdict: OverallVerdict = "insufficient_data"

    # Every gap found in the paper, open or resolved. This is the gaps report.
    gaps: list[Gap] = Field(default_factory=list)
    iterations: list[Iteration] = Field(default_factory=list)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ReproStandard":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def json_schema(cls) -> str:
        return json.dumps(cls.model_json_schema(), indent=2)
