"""Model cards: everything needed to rebuild a paper's data-driven (black-box) model.

A card is extracted like any other feature: every field is provenance-tagged, and what the
paper (or its SI, repository, deposited data) does not specify stays missing and becomes a
gap. The black-box twin evaluates the rebuilt model on transport-resolved conditions.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .rig import TaggedFloat, TaggedStr

ModelFamily = Literal["gaussian_process", "neural_network", "other"]

FeatureKind = Literal[
    "flow_fraction",   # sum(flows of `numerator` pumps) / sum(flows of `denominator` pumps)
    "residence_time",  # time the fluid element spent in `node` [s]
    "temperature",     # setpoint of `node` [degC]
    "constant",        # fixed physical value (`value`)
]


def _f():
    return Field(default_factory=TaggedFloat)


def _s():
    return Field(default_factory=TaggedStr)


class ModelInput(BaseModel):
    """One model input: how to compute it from the rig, and how the model normalizes it.

    The model sees (x - low) / (high - low), with x in `unit` after `scale` is applied to the
    twin's base unit (s for residence_time, degC for temperature, - for fractions).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: FeatureKind
    column: Optional[str] = None  # training-data column holding this input
    definition: TaggedStr = _s()  # the paper's own formula / wording
    node: Optional[str] = None
    numerator: list[str] = Field(default_factory=list)
    denominator: list[str] = Field(default_factory=list)
    value: TaggedFloat = _f()
    unit: Optional[str] = None
    scale: float = 1.0  # base unit -> `unit` (e.g. 1/60 for s -> min)
    low: TaggedFloat = _f()
    high: TaggedFloat = _f()


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str  # claim metric name, e.g. emission_wavelength
    column: Optional[str] = None
    unit: Optional[str] = None
    definition: TaggedStr = _s()
    low: TaggedFloat = _f()   # normalized = (y - low) / (high - low); high < low inverts
    high: TaggedFloat = _f()


class ValidationProtocol(BaseModel):
    """Machine-readable form of the paper's validation, so it can be re-run exactly."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["kfold"] = "kfold"
    folds: int = 5
    pre_shuffle_seed: Optional[int] = None  # rows shuffled before splitting (pandas sample)
    split_seed: Optional[int] = None        # KFold(shuffle=True, random_state=...)
    metric: Literal["pearson_r2", "r2"] = "r2"


class ModelCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    family: ModelFamily
    purpose: Optional[str] = None
    inputs: list[ModelInput] = Field(default_factory=list)
    outputs: list[ModelOutput] = Field(default_factory=list)

    # Software
    library: TaggedStr = _s()
    library_version: TaggedStr = _s()
    code: TaggedStr = _s()  # repository / file / commit

    # Gaussian process
    kernel: TaggedStr = _s()
    mean_function: TaggedStr = _s()
    likelihood: TaggedStr = _s()
    priors: TaggedStr = _s()
    output_transform: TaggedStr = _s()
    multi_output: TaggedStr = _s()  # independent per output, multitask, ...

    # Neural network
    architecture: TaggedStr = _s()
    activation: TaggedStr = _s()
    optimizer: TaggedStr = _s()
    learning_rate: TaggedFloat = _f()
    epochs: TaggedFloat = _f()
    batch_size: TaggedFloat = _f()
    regularization: TaggedStr = _s()
    initialization: TaggedStr = _s()

    # Training and validation
    hyperparameter_fitting: TaggedStr = _s()
    training_data: TaggedStr = _s()  # where the exact training set lives (URL / table)
    training_data_sha256: Optional[str] = None
    training_data_normalized: Optional[bool] = None  # columns already (x-low)/(high-low)?
    n_training_points: TaggedFloat = _f()
    validation: TaggedStr = _s()  # the paper's wording
    validation_protocol: Optional[ValidationProtocol] = None
    metric_definitions: TaggedStr = _s()  # e.g. "R2 = squared Pearson correlation"
    seeds: TaggedStr = _s()
