"""Training data for a model card: fetched once, cached, and checked against its sha256.

Data are not vendored: papers' deposited data and code keep their own licences. The cache
lives in .cache/xp_plus/ (git-ignored).
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from ..schema import ModelCard

CACHE = Path(__file__).resolve().parents[2] / ".cache" / "xp_plus"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def training_data_path(card: ModelCard, *, offline: bool = False) -> Path:
    """Local path to the card's training data, downloading it if needed."""
    if not card.training_data.known:
        raise ValueError(f"model '{card.id}': training data location not reported")
    where = card.training_data.value
    if not where.startswith(("http://", "https://")):
        path = Path(where)
    else:
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"{card.id}-{Path(where).name}"
        if not path.exists():
            if offline:
                raise FileNotFoundError(f"{path} not cached and offline=True")
            with urllib.request.urlopen(where, timeout=60) as resp:
                path.write_bytes(resp.read())
    if card.training_data_sha256 and sha256(path) != card.training_data_sha256:
        raise ValueError(f"model '{card.id}': training data at {path} does not match its sha256")
    return path
