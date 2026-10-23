"""Optical properties + the instrument-response forward model (UV-4).

Turns a simulated cell composition into a simulated instrument readout, in layers:

1. **Optical properties** (``data/optical_properties.toml``): per species, an effective absorption
   ``eps(lambda)`` and/or a photoluminescence shape ``g(lambda)`` (+ excitation / quantum yield).
2. **Physical interaction**: Beer-Lambert ``A(lambda,t) = sum_i eps_i(lambda) c_i(t) L`` for
   absorption; ``I(lambda,t) = sum_i QY_i eps_i(ex) c_i L g_i(lambda)`` for photoluminescence.
3. **Instrument transfer**: the spectrometer's finite resolution (slit-function blur), the usable
   wavelength range (spectrometer ∩ light source), optional non-ideal deviations from Beer-Lambert
   (stray light, detector saturation), and integration-time-dependent noise.

``eps`` is an *effective* per-species absorptivity at the twin's (normalized) concentration scale —
the spectral generalization of the lumped scalar ``A_full`` — so ``A`` stays ~O(1) for ``c`` ~O(1).
The placeholder spectra in the TOML are meant to be replaced by digitized literature or the user's
own MEASURED spectra (same shape) for a faithful readout.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

_DATA = Path(__file__).with_name("data")
_OPTICAL_PATH = _DATA / "optical_properties.toml"


@dataclass(frozen=True)
class OpticalProperty:
    """One species' reference spectrum for one measurement kind."""

    species: str
    kind: str                          # "absorption" | "emission"
    axis: tuple                        # wavelength/wavenumber samples (axis_unit)
    values: tuple                      # eps (absorption) or normalized intensity (emission)
    axis_unit: str = "nm"
    excitation_nm: float | None = None
    quantum_yield: float = 1.0


def load_optical_models(path: str | Path | None = None) -> list[OpticalProperty]:
    """Load the per-species optical-property library (every ``[[optical]]`` entry)."""
    with open(Path(path) if path else _OPTICAL_PATH, "rb") as fh:
        doc = tomllib.load(fh)
    out: list[OpticalProperty] = []
    for e in doc.get("optical", []):
        kind = e.get("kind", "absorption")
        vals = e.get("epsilon") if kind == "absorption" else e.get("intensity")
        out.append(OpticalProperty(
            species=e["species"], kind=kind,
            axis=tuple(float(x) for x in e["axis"]),
            values=tuple(float(x) for x in (vals or [])),
            axis_unit=e.get("axis_unit", "nm"),
            excitation_nm=e.get("excitation_nm"),
            quantum_yield=float(e.get("quantum_yield", 1.0)),
        ))
    return out


def scale_models(models: list[OpticalProperty], scales: dict[str, float],
                 kind: str = "absorption") -> list[OpticalProperty]:
    """Return a copy of ``models`` with each species' ``kind`` spectrum multiplied by
    ``scales[species]`` (default 1.0). Used to apply a fitted per-species absorptivity scale
    (UV-5) and to build the calibrated override set fed back via ``ResolvedFlowsheet.optical_models``."""
    out: list[OpticalProperty] = []
    for p in models:
        s = scales.get(p.species, 1.0) if p.kind == kind else 1.0
        out.append(p if s == 1.0 else OpticalProperty(
            species=p.species, kind=p.kind, axis=p.axis,
            values=tuple(v * s for v in p.values), axis_unit=p.axis_unit,
            excitation_nm=p.excitation_nm, quantum_yield=p.quantum_yield))
    return out


def interp_spectrum(axis_src: NDArray, values: NDArray, axis_dst: NDArray) -> NDArray:
    """Resample a spectrum ``values`` (n_src, n_t) from ``axis_src`` onto ``axis_dst`` (per column)."""
    axis_src = np.asarray(axis_src, float)
    if values.shape[0] == len(axis_dst) and np.allclose(axis_src, axis_dst):
        return values
    return np.stack([np.interp(axis_dst, axis_src, values[:, j], left=0.0, right=0.0)
                     for j in range(values.shape[1])], axis=1)


@dataclass
class InstrumentConfig:
    """Resolved per-instrument readout configuration (from the flow cell + attachments)."""

    path_length_mm: float = 10.0
    signal_kind: str = "spectrum_vs_time"   # spectrum_vs_time | scalar_vs_time | sampled_trace
    observable: str = "absorbance"          # "absorbance" | "emission"
    axis_unit: str = "nm"
    wl_min: float = 200.0
    wl_max: float = 1100.0
    resolution_nm: float = 1.0
    integration_ms: float = 10.0
    averages: int = 1
    # non-ideal deviations from Beer-Lambert (0/None => ideal)
    stray_light: float = 0.0                # stray-light fraction
    a_saturation: float | None = None       # cap on measured absorbance
    noise: bool = False                     # add integration-time-dependent detector noise

    @classmethod
    def from_dict(cls, d: dict) -> "InstrumentConfig":
        fields = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**fields)


def instrument_axis(cfg: InstrumentConfig, *, max_points: int = 600) -> NDArray:
    """The wavelength grid the instrument reports on: its usable range at (capped) resolution."""
    lo, hi = float(cfg.wl_min), float(cfg.wl_max)
    if hi <= lo:
        lo, hi = 200.0, 900.0
    step = max(float(cfg.resolution_nm), (hi - lo) / max_points, 0.5)
    n = int((hi - lo) / step) + 1
    return lo + step * np.arange(n)


def _interp_onto(axis: NDArray, prop: OpticalProperty) -> NDArray:
    """A property's spectrum interpolated onto ``axis``; 0 outside its defined range."""
    return np.interp(axis, np.asarray(prop.axis, float), np.asarray(prop.values, float),
                     left=0.0, right=0.0)


def absorbance_spectrum(axis: NDArray, cell: NDArray, names: list[str],
                        models: list[OpticalProperty], path_length_mm: float) -> NDArray:
    """Beer-Lambert sum ``A(lambda,t) = sum_i eps_i(lambda) c_i(t) L`` -> ``(n_lambda, n_t)``."""
    L = float(path_length_mm) / 10.0                      # mm -> cm
    absn = {p.species: p for p in models if p.kind == "absorption"}
    A = np.zeros((len(axis), cell.shape[1]))
    for i, sp in enumerate(names):
        p = absn.get(sp)
        if p is None:
            continue
        eps = _interp_onto(axis, p)                       # (n_lambda,)
        A += np.outer(eps, cell[i]) * L                   # (n_lambda, n_t)
    return A


def emission_spectrum(axis: NDArray, cell: NDArray, names: list[str],
                      models: list[OpticalProperty], path_length_mm: float) -> NDArray:
    """Photoluminescence ``I(lambda,t) = sum_i QY_i eps_i(ex) c_i L g_i(lambda)`` (dilute-linear)."""
    L = float(path_length_mm) / 10.0
    absn = {p.species: p for p in models if p.kind == "absorption"}
    I = np.zeros((len(axis), cell.shape[1]))
    for p in (m for m in models if m.kind == "emission"):
        if p.species not in names:
            continue
        i = names.index(p.species)
        ap = absn.get(p.species)
        eps_ex = (float(np.interp(p.excitation_nm, ap.axis, ap.values, left=0.0, right=0.0))
                  if (ap is not None and p.excitation_nm is not None) else 1.0)
        g = _interp_onto(axis, p)
        I += np.outer(g, cell[i] * eps_ex * L * p.quantum_yield)
    return I


def _slit_blur(spectrum: NDArray, axis: NDArray, fwhm: float) -> NDArray:
    """Convolve along wavelength with a Gaussian slit function of the given FWHM (axis units)."""
    if fwhm <= 0 or len(axis) < 3:
        return spectrum
    step = float(np.mean(np.diff(axis)))
    sigma = (fwhm / 2.3548) / step                        # in samples
    if sigma < 1e-2:
        return spectrum
    half = int(max(1, round(3 * sigma)))
    x = np.arange(-half, half + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    # edge-normalized convolution: divide by the kernel weight that fell inside the band, so a
    # flat spectrum stays flat (no boundary droop) and the blur is exactly identity on constants.
    norm = np.convolve(np.ones(spectrum.shape[0]), k, mode="same")
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same") / norm, 0, spectrum)


def apply_transfer(spectrum: NDArray, axis: NDArray, cfg: InstrumentConfig,
                   rng: np.random.Generator | None = None) -> NDArray:
    """Apply the instrument's spectral response to an ideal absorbance/emission spectrum.

    Slit-function blur (finite resolution) -> optional non-ideal Beer-Lambert deviations (stray
    light, detector saturation) -> optional integration-time-dependent noise (SNR ~ sqrt(integ x
    averages)). All deviations default off, so the ideal Beer-Lambert sum is recovered exactly."""
    out = _slit_blur(spectrum, axis, cfg.resolution_nm)
    if cfg.observable == "absorbance" and cfg.stray_light > 0:
        # stray light floors the transmittance, flattening high-absorbance peaks
        T = (10.0 ** (-out) + cfg.stray_light) / (1.0 + cfg.stray_light)
        out = -np.log10(np.clip(T, 1e-12, None))
    if cfg.a_saturation is not None:
        out = np.minimum(out, cfg.a_saturation)
    if cfg.noise and rng is not None:
        sigma = 0.002 / math.sqrt(max(cfg.integration_ms * max(cfg.averages, 1), 1e-6) / 10.0)
        out = out + rng.normal(0.0, sigma, size=out.shape)
    return out


def build_instrument_signals(fs, taps: dict | None, species_names: list[str],
                             instrument_specs: dict | None, *,
                             optical_models: list[OpticalProperty] | None = None,
                             rng: np.random.Generator | None = None) -> dict:
    """Turn each analyzer tap into an observable signal entry on ``SimResult.signals``.

    Always records the base ``{subtype, kind, names, cell}``; when the instrument has a resolved
    config and optical models exist, also attaches the simulated spectrum (``axis`` + ``values``)
    for a ``spectrum_vs_time`` instrument. Returns ``{}`` for no taps."""
    if not taps:
        return {}
    models = optical_models if optical_models is not None else load_optical_models()
    specs = instrument_specs or {}
    names = list(species_names)
    out: dict = {}
    for nid, cell in taps.items():
        node = fs.nodes.get(nid)
        entry = {"subtype": getattr(node, "subtype", None),
                 "kind": getattr(node, "kind", "flow_through"),
                 "names": names, "cell": cell}
        cell2 = np.atleast_2d(np.asarray(cell, float))    # scalar tap -> (1, n_t)
        cfg_d = specs.get(nid)
        if cfg_d is not None and cell2.shape[0] == len(names) and len(names) > 0:
            cfg = InstrumentConfig.from_dict(cfg_d)
            if cfg.signal_kind == "spectrum_vs_time":
                axis = instrument_axis(cfg)
                if cfg.observable == "emission":
                    spec = emission_spectrum(axis, cell2, names, models, cfg.path_length_mm)
                else:
                    spec = absorbance_spectrum(axis, cell2, names, models, cfg.path_length_mm)
                spec = apply_transfer(spec, axis, cfg, rng)
                entry.update(signal_kind="spectrum_vs_time", observable=cfg.observable,
                             axis=axis, axis_unit=cfg.axis_unit, values=spec)
        out[nid] = entry
    return out
