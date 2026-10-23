"""Rebuild a paper's model from its card and evaluate it on physical inputs.

Backends:
    botorch         one SingleTaskGP per output, installed BoTorch's defaults
    botorch_legacy  the same with BoTorch < 0.12 defaults (Matern-5/2, Gamma priors, no Standardize)
    sklearn         GaussianProcessRegressor, constant * ARD-RBF + white noise (no torch needed)
Neural networks: TODO (the card already records what a rebuild needs).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from ..schema import ModelCard
from .data import training_data_path


def _bounds(items, what):
    out = []
    for it in items:
        if not (it.low.known and it.high.known):
            raise ValueError(f"{what} '{it.name}': normalization bounds not reported")
        out.append((it.low.value, it.high.value))
    lo, hi = np.array(out).T
    return lo, hi


def load_training(card: ModelCard) -> tuple[np.ndarray, np.ndarray]:
    """Training (X, Y) in the model's normalized space, as the paper trained on it."""
    import pandas as pd
    df = pd.read_csv(training_data_path(card))
    X = df[[i.column for i in card.inputs]].to_numpy(float)
    Y = df[[o.column for o in card.outputs]].to_numpy(float)
    if not card.training_data_normalized:
        (xl, xh), (yl, yh) = _bounds(card.inputs, "input"), _bounds(card.outputs, "output")
        X, Y = (X - xl) / (xh - xl), (Y - yl) / (yh - yl)
    return X, Y


class _BoTorchGP:
    """SingleTaskGP with the installed BoTorch's defaults (>= 0.12: RBF, dimension-scaled
    lognormal lengthscale prior, Standardize outcome transform)."""

    name = "botorch"

    def _kwargs(self):
        return {}

    def fit(self, X, Y):
        import torch
        from botorch.fit import fit_gpytorch_mll
        from botorch.models import SingleTaskGP
        from gpytorch.mlls import ExactMarginalLogLikelihood
        self.models = []
        for j in range(Y.shape[1]):
            m = SingleTaskGP(torch.tensor(X, dtype=torch.double), torch.tensor(Y[:, j:j + 1], dtype=torch.double),
                             **self._kwargs())
            fit_gpytorch_mll(ExactMarginalLogLikelihood(m.likelihood, m))
            self.models.append(m)
        return self

    def predict(self, X):
        import torch
        Xt = torch.tensor(X, dtype=torch.double)
        means, stds = [], []
        with torch.no_grad():
            for m in self.models:
                post = m.posterior(Xt)
                means.append(post.mean.squeeze(-1).numpy())
                stds.append(post.variance.clamp_min(0).sqrt().squeeze(-1).numpy())
        return np.stack(means, 1), np.stack(stds, 1)

    @staticmethod
    def version() -> str:
        import botorch, gpytorch, torch
        return f"botorch {botorch.__version__} / gpytorch {gpytorch.__version__} / torch {torch.__version__}"


class _BoTorchLegacyGP(_BoTorchGP):
    """SingleTaskGP with the defaults of BoTorch < 0.12: ScaleKernel(Matern-5/2, ARD) with
    Gamma(3, 6) lengthscale and Gamma(2, 0.15) outputscale priors, Gamma(1.1, 0.05) noise prior,
    and no outcome transform. For papers whose code predates the 0.12 default change."""

    name = "botorch_legacy"

    def _kwargs(self):
        from gpytorch.kernels import MaternKernel, ScaleKernel
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.priors import GammaPrior
        d = self._d
        return dict(covar_module=ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=d, lengthscale_prior=GammaPrior(3.0, 6.0)),
                                             outputscale_prior=GammaPrior(2.0, 0.15)),
                    likelihood=GaussianLikelihood(noise_prior=GammaPrior(1.1, 0.05)), outcome_transform=None)

    def fit(self, X, Y):
        self._d = X.shape[1]
        return super().fit(X, Y)

    @staticmethod
    def version() -> str:
        return _BoTorchGP.version() + " (pre-0.12 defaults)"


class _SklearnGP:
    name = "sklearn"

    def fit(self, X, Y):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
        d = X.shape[1]
        self.models = []
        for j in range(Y.shape[1]):
            k = ConstantKernel() * RBF(length_scale=np.ones(d)) + WhiteKernel(1e-3)
            self.models.append(GaussianProcessRegressor(k, normalize_y=True, n_restarts_optimizer=3,
                                                        random_state=0).fit(X, Y[:, j]))
        return self

    def predict(self, X):
        out = [m.predict(X, return_std=True) for m in self.models]
        return np.stack([o[0] for o in out], 1), np.stack([o[1] for o in out], 1)

    @staticmethod
    def version() -> str:
        import sklearn
        return f"scikit-learn {sklearn.__version__}"


BACKENDS = {"botorch": _BoTorchGP, "botorch_legacy": _BoTorchLegacyGP, "sklearn": _SklearnGP}


@dataclass
class BlackBoxModel:
    """A fitted card model that takes PHYSICAL inputs and returns PHYSICAL outputs."""

    card: ModelCard
    backend: str = "botorch"
    _impl: object = field(default=None, repr=False)

    def fit(self, X: np.ndarray | None = None, Y: np.ndarray | None = None) -> "BlackBoxModel":
        if self.card.family != "gaussian_process":
            raise NotImplementedError(f"family '{self.card.family}' not supported yet")
        if X is None:
            X, Y = load_training(self.card)
        self._impl = BACKENDS[self.backend]().fit(X, Y)
        return self

    @property
    def input_names(self) -> list[str]:
        return [i.name for i in self.card.inputs]

    @property
    def output_names(self) -> list[str]:
        return [o.name for o in self.card.outputs]

    def backend_version(self) -> str:
        return BACKENDS[self.backend].version()

    def normalize(self, X_phys: np.ndarray) -> np.ndarray:
        lo, hi = _bounds(self.card.inputs, "input")
        return (X_phys - lo) / (hi - lo)

    def predict_normalized(self, Xn: np.ndarray):
        return self._impl.predict(Xn)

    def predict(self, X_phys: np.ndarray):
        """(mean, std) in physical output units for X in physical input units (model units)."""
        lo, hi = _bounds(self.card.outputs, "output")
        mean, std = self._impl.predict(self.normalize(np.atleast_2d(X_phys)))
        return lo + mean * (hi - lo), std * np.abs(hi - lo)


def danamic_factory(card_json: str, backend: str = "botorch") -> "_DanamicAdapter":
    """Entry point Danamic's black_box engine loads by name (xp_plus.blackbox.model:danamic_factory)."""
    card = ModelCard.model_validate(json.loads(card_json))
    return _DanamicAdapter(BlackBoxModel(card, backend).fit())


class _DanamicAdapter:
    """Danamic hands over features in base units (s, degC, fractions); apply each input's scale."""

    def __init__(self, model: BlackBoxModel):
        self.model = model
        self.input_names = model.input_names
        self.output_names = model.output_names
        self.scales = np.array([i.scale for i in model.card.inputs])

    def predict(self, X_base: np.ndarray):
        return self.model.predict(np.asarray(X_base) * self.scales)
