"""Re-run a paper's model validation exactly as its card describes (gate levels 2-3)."""
from __future__ import annotations

import numpy as np

from ..schema import ComputationalRecord, ModelCard, Quantity
from .data import sha256, training_data_path
from .model import BACKENDS, BlackBoxModel, load_training


def _metric(kind: str, y: np.ndarray, p: np.ndarray) -> float:
    if kind == "pearson_r2":
        return float(np.corrcoef(y, p)[0, 1] ** 2)
    return float(1.0 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2))


def cross_validate(card: ModelCard, backend: str = "botorch") -> tuple[np.ndarray, np.ndarray]:
    """Out-of-fold predictions and actuals (normalized space), in the paper's row order."""
    from sklearn.model_selection import KFold
    proto = card.validation_protocol
    if proto is None:
        raise ValueError(f"model '{card.id}': validation protocol not reported")
    X, Y = load_training(card)
    if proto.pre_shuffle_seed is not None:  # same draw as pandas DataFrame.sample(frac=1, random_state=seed)
        idx = np.random.RandomState(proto.pre_shuffle_seed).choice(len(X), len(X), replace=False)
        X, Y = X[idx], Y[idx]
    kf = KFold(n_splits=proto.folds, shuffle=proto.split_seed is not None, random_state=proto.split_seed)
    preds, acts = [], []
    for tr, te in kf.split(X):
        m = BlackBoxModel(card, backend).fit(X[tr], Y[tr])
        preds.append(m.predict_normalized(X[te])[0])
        acts.append(Y[te])
    return np.vstack(preds), np.vstack(acts)


def reproduce_validation(card: ModelCard, backend: str = "botorch") -> ComputationalRecord:
    """Metrics keyed like claims: cv_<metric>_<output> (e.g. cv_r2_emission_wavelength)."""
    pred, act = cross_validate(card, backend)
    kind = card.validation_protocol.metric
    tag = "r2"  # claim metric names use "r2" for both definitions; the card says which one
    metrics = {f"cv_{tag}_{o.name}": Quantity(value=_metric(kind, act[:, j], pred[:, j]))
               for j, o in enumerate(card.outputs)}
    path = training_data_path(card)
    notes = [f"metric: {kind}", f"{card.validation_protocol.folds}-fold CV, pre-shuffle seed "
             f"{card.validation_protocol.pre_shuffle_seed}, split seed {card.validation_protocol.split_seed}"]
    if not card.library_version.known:
        notes.append("paper's library version not reported; defaults of the installed version used")
    return ComputationalRecord(model_id=card.id, backend=f"{backend}: {BACKENDS[backend].version()}",
                               training_data_sha256=sha256(path), n_training_points=len(act),
                               metrics=metrics, assumptions=notes)
