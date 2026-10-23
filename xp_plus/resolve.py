"""Close gaps: write Resolution values into PaperFeatures at their target paths."""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel

from .schema import PaperFeatures, Resolution, Tagged


def _child(obj, part: str):
    """Step one path segment: list items are addressed by id / key / name, not index."""
    if isinstance(obj, list):
        for item in obj:
            key = getattr(item, "id", None) or getattr(item, "key", None) or getattr(item, "name", None)
            if key == part:
                return item
        raise KeyError(part)
    if isinstance(obj, dict):
        return obj[part]
    if isinstance(obj, BaseModel) and part in type(obj).model_fields:
        return getattr(obj, part)
    raise KeyError(part)


def apply_resolution(features: PaperFeatures, res: Resolution) -> None:
    """Set the Tagged value at `res.target` in place. Raises KeyError for an unknown path."""
    if res.provenance == "missing":
        raise ValueError(f"{res.target}: a resolution cannot have provenance 'missing'")
    *parents, leaf = res.target.split(".")
    obj = features
    for part in parents:
        obj = _child(obj, part)
    fields = dict(value=res.value, provenance=res.provenance, source=res.source, note=res.note)
    if isinstance(obj, dict):  # e.g. reservoir contents: species -> concentration
        obj[leaf] = Tagged[float](**fields)
    elif isinstance(obj, BaseModel) and isinstance(getattr(obj, leaf, None), Tagged):
        setattr(obj, leaf, type(getattr(obj, leaf))(**fields))  # keeps Tagged[float] / Tagged[str]
    else:
        raise KeyError(f"{res.target}: not a provenance-tagged field")


def apply_resolutions(features: PaperFeatures, resolutions: Iterable[Resolution]) -> PaperFeatures:
    """Return a copy of `features` with every resolution applied."""
    out = features.model_copy(deep=True)
    for res in resolutions:
        apply_resolution(out, res)
    return out
