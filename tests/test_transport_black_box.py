"""Black-box fidelity: analytical transport + a pluggable data model."""
import math

import numpy as np
import pytest

from fluidsim_twin.schema import (
    BlackBoxDoc, EdgeDoc, FeatureDoc, NodeDoc, PlatformDoc, PumpSpec, RtdSpec, RunDoc, ScheduleDoc,
)
from fluidsim_twin.service import TwinService

IDEAL = dict(gain=1.0, beta=0.0, theta=0.0, tau_fast=1e-3, w_slow=0.0)
V_R, V_D = 1113.0, 228.0
TAU0, ALPHA = 1.0, 0.6  # min, min/min
T_STEADY, T_RAMP, DT = 180.0, 1200.0, 2.0


def _schedules():
    """Two pumps (3:1) at tau0 for 3 min, then the DFE ramp tau_ins = tau0 + alpha t (ZOH, 2 s)."""
    ts = [0.0] + list(T_STEADY + np.arange(0.0, T_RAMP, DT))
    q = [V_R / TAU0] + [V_R / (TAU0 + ALPHA * (k + 0.5) * DT / 60) for k in range(len(ts) - 1)]
    return {"a": ScheduleDoc(t_breaks=ts, values=[0.75 * x for x in q]),
            "b": ScheduleDoc(t_breaks=ts, values=[0.25 * x for x in q])}


def _platform():
    src = lambda i: NodeDoc(id=i, type="source", pump=PumpSpec(**IDEAL))
    return PlatformDoc(platform_id="dfe", nodes=[
        src("a"), src("b"),
        NodeDoc(id="mix", type="mixer", V=1.0, rtd=RtdSpec(model="plug")),
        NodeDoc(id="reactor", type="reactor", V=V_R, rtd=RtdSpec(model="plug"), temperature_K=557.15),
        NodeDoc(id="cell", type="sink", kind="cell"),
    ], edges=[EdgeDoc(src="a", dst="mix"), EdgeDoc(src="b", dst="mix"), EdgeDoc(src="mix", dst="reactor"),
              EdgeDoc(src="reactor", dst="cell", id_mm=0.762, length_mm=V_D / (math.pi * 0.381 ** 2))])


def _run(features, weights):
    return RunDoc(run_id="r", platform_ref="dfe", grid={"t0": 0.0, "t_end": T_STEADY + T_RAMP, "dt": 1.0},
                  schedules=_schedules(), fidelity="black_box",
                  black_box=BlackBoxDoc(model="fluidsim_twin.engines.black_box:linear_model",
                                        args={"weights": weights, "bias": [0.0] * len(weights)},
                                        features=features, outputs=[f"y{i}" for i in range(len(weights))]))


def test_experienced_residence_time_matches_dfe_mapping_equation():
    """Delgado-Licona et al. (2025) Eq. 2: tau = (1 - e^-a) e^(-a Vd/Vr) (t_m + tau0/a)."""
    feats = [FeatureDoc(name="tau", kind="residence_time", node="reactor")]
    res = TwinService().simulate(_platform(), _run(feats, [[1.0 / 60]]))  # output = tau [min]
    sig = res.signals["cell:black_box"]
    tg, tau = np.asarray(res.tg), sig["cell"][0]
    tm = (tg - T_STEADY) / 60.0
    eq2 = (1 - math.exp(-ALPHA)) * math.exp(-ALPHA * V_D / V_R) * (tm + TAU0 / ALPHA)
    # Eq. 2 holds once every element in the reactor entered after the ramp began (SI §4, t*).
    window = (tm > 3.0) & (tm < T_RAMP / 60)
    assert np.nanmax(np.abs(tau[window] - eq2[window])) < 0.02  # min


def test_flow_fraction_temperature_and_constant_features():
    feats = [FeatureDoc(name="xa", kind="flow_fraction", node="reactor", numerator=["a"], denominator=["a", "b"]),
             FeatureDoc(name="T", kind="temperature", node="reactor"),
             FeatureDoc(name="c", kind="constant", value=2.5)]
    res = TwinService().simulate(_platform(), _run(feats, [[1, 0, 0], [0, 1, 0], [0, 0, 1]]))
    y = res.signals["cell:black_box"]["cell"]
    late = np.isfinite(y[0])
    assert np.allclose(y[0][late], 0.75) and np.allclose(y[1][late], 284.0) and np.allclose(y[2][late], 2.5)
    assert not late[0]  # nothing has reached the cell at t = 0


def test_capabilities_reject_unknown_nodes():
    feats = [FeatureDoc(name="tau", kind="residence_time", node="nope")]
    assert any("unknown node" in e for e in TwinService().validate(_platform(), _run(feats, [[1.0]])))
