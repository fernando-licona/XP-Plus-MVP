"""Run the Danamic twin headlessly and turn its output into predicted figures of merit."""
from __future__ import annotations

from ..schema import PaperFeatures, Quantity, TwinRecord
from .gate import reactor_residence_time_s
from .to_danamic import TwinOptions, to_danamic


class TwinBuildError(RuntimeError):
    def __init__(self, errors: list[str]):
        super().__init__("Danamic rejected the twin: " + "; ".join(errors))
        self.errors = errors


def dispersion_f_curve(t, t_avg, bo):
    """SI Eq. 1 of Delgado-Licona et al. (2025): the step response of the dispersion model."""
    import numpy as np
    from scipy.special import erf
    k = np.sqrt(bo / 4.0)
    return 0.5 * (erf(k * (t / t_avg - 1.0)) + erf(k))


def fit_f_curve(t, a, t0: float, t_guess: float) -> tuple[float, float]:
    """Normalize the detector signal after a step at t0 to an F-curve; fit (t_avg [s], Bo)."""
    import numpy as np
    from scipy.optimize import curve_fit
    before, after = np.interp(t0, t, a), a[-1]
    if abs(after - before) < 1e-12:
        raise ValueError("no step in the detector signal")
    mask = t > t0
    tt, ff = t[mask] - t0, (a[mask] - before) / (after - before)
    (t_avg, bo), _ = curve_fit(dispersion_f_curve, tt, ff, p0=(t_guess, 200.0),
                               bounds=([1e-6, 1.0], [np.inf, 1e7]))
    return float(t_avg), float(bo)


def _first_crossing(x, y, s, target):
    """Interpolate (y, s) where x first crosses target, using finite consecutive points only."""
    import numpy as np
    on = np.isfinite(x) & np.isfinite(y) & np.isclose(x, target, rtol=0, atol=1e-6 * max(1.0, abs(target)))
    if on.any():  # sits exactly at the target, e.g. the steady state before a ramp
        i = np.argmax(on)
        return y[i], s[i]
    ok = np.isfinite(x[:-1]) & np.isfinite(x[1:]) & np.isfinite(y[:-1]) & np.isfinite(y[1:])
    hit = np.nonzero(ok & ((x[:-1] - target) * (x[1:] - target) <= 0) & (x[:-1] != x[1:]))[0]
    if hit.size == 0:
        return None
    i = hit[0]
    w = (target - x[i]) / (x[i + 1] - x[i])
    return y[i] + w * (y[i + 1] - y[i]), s[i] + w * (s[i + 1] - s[i])


def black_box_predictions(f: PaperFeatures, options: TwinOptions, res, cell_id: str) -> dict[str, Quantity]:
    """For each claim on a model output with an `at` condition, read the twin's output where the
    transport-resolved model inputs reach that condition (the steady-state-equivalent point)."""
    from ..compare import claim_key
    card = next(m for m in f.models if m.id == options.black_box)
    sig = res.signals[f"{cell_id}:black_box"]
    scale = {i.name: i.scale for i in card.inputs}
    units = {o.name: o.unit for o in card.outputs}
    out = {}
    for c in f.claims:
        if c.metric not in sig["names"] or len(c.at) != 1:
            continue  # TODO: claims conditioned on more than one input
        (name, target), = c.at.items()
        j = sig["names"].index(c.metric)
        hit = _first_crossing(sig["features"][name] * scale[name], sig["cell"][j], sig["std"][j], target)
        if hit is not None:
            out[claim_key(c)] = Quantity(value=float(hit[0]), unit=units[c.metric], std=float(hit[1]))
    return out


def predict(f: PaperFeatures, options: TwinOptions | None = None) -> TwinRecord:
    """Simulate the protocol and report predictions keyed by claim metric name.

    Always: residence_time (reactor volume / flow at t = 0).
    Tracer step (a measurement with observable "f_curve" and t0_step): fit SI-Eq.-1-style
    mean_residence_time and bodenstein_number to the simulated detector signal, as the paper did.
    Otherwise: tracer_t50 for a step at t = 0.
    Reactive outputs (conversion, yield, QD optics) are not modelled: TODO.
    """
    import numpy as np
    from fluidsim_twin.service import TwinService

    inputs = to_danamic(f, options)
    svc = TwinService()
    errors = svc.validate(inputs.platform, inputs.run)
    if errors:
        raise TwinBuildError(errors)
    res = svc.simulate(inputs.platform, inputs.run)
    t, a = np.asarray(res.t), np.asarray(res.A)

    predictions: dict[str, Quantity] = {}
    tau = reactor_residence_time_s(f)
    if tau is not None:
        predictions["residence_time"] = Quantity(value=tau, unit="s")

    if inputs.run.black_box is not None:
        predictions.update(black_box_predictions(f, options, res, inputs.cell_id))

    fcurve = next((m for m in f.measurements if m.observable == "f_curve" and m.t0_step), None)
    if fcurve is not None:
        t0 = inputs.step_times[fcurve.t0_step]
        t_avg, bo = fit_f_curve(t, a, t0, t_guess=tau or 60.0)
        predictions["mean_residence_time"] = Quantity(value=t_avg, unit="s")
        predictions["bodenstein_number"] = Quantity(value=bo)
    elif a.size and a[-1] > 0:
        predictions["tracer_t50"] = Quantity(value=float(t[np.argmax(a >= 0.5 * a[-1])]), unit="s")

    notes = ["residence_time = reactor volume / total flow (nominal, as the paper defines it)"]
    if fcurve is not None:
        notes.append(f"F-curve fitted with SI Eq. 1 from the '{fcurve.t0_step}' step at the detector")
    return TwinRecord(fidelity=res.fidelity_used, predictions=predictions,
                      assumptions=inputs.assumptions + notes)
