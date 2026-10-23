"""Protocol -> timeline: when each step happens and what every pump is commanded to do.

Semantics (kept deliberately small): steps run in order from t = 0; `set_flow_rate` is
instantaneous (component = pump, parameters.flow_rate_uL_min); `wait` advances time by
duration_s; `residence_time_ramp` scales every running pump so the nominal residence time
V / sum(Q) follows tau0 + alpha * t (min) for duration_s at constant stream ratios
(parameters: tau0_min, alpha, volume_uL); any other action is recorded and has no effect.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import PaperFeatures


@dataclass
class Timeline:
    schedules: dict[str, tuple[list[float], list[float]]] = field(default_factory=dict)  # pump -> (t_s, uL/min)
    step_times: dict[str, float] = field(default_factory=dict)  # step id -> t [s]
    t_end: float = 0.0


def timeline(f: PaperFeatures) -> Timeline:
    tl, t = Timeline(), 0.0
    for step in f.protocol:
        tl.step_times[step.id] = t
        if step.action == "set_flow_rate":
            q = step.parameters.get("flow_rate_uL_min")
            if step.component is None or q is None or not q.known:
                raise ValueError(f"protocol step '{step.id}': set_flow_rate needs a pump and flow_rate_uL_min")
            ts, vs = tl.schedules.setdefault(step.component, ([], []))
            if ts and ts[-1] == t:
                vs[-1] = q.value
            else:
                ts.append(t)
                vs.append(q.value)
        elif step.action == "wait":
            if not step.duration_s.known:
                raise ValueError(f"protocol step '{step.id}': wait needs duration_s")
            t += step.duration_s.value
        elif step.action == "residence_time_ramp":
            t = _ramp(tl, step, t)
    tl.t_end = t
    return tl


RAMP_DT_S = 2.0  # schedule resolution of a ramp


def _ramp(tl: Timeline, step, t: float) -> float:
    p = {k: v.value for k, v in step.parameters.items()}
    needed = ("tau0_min", "alpha", "volume_uL")
    if not all(p.get(k) is not None for k in needed) or not step.duration_s.known:
        raise ValueError(f"protocol step '{step.id}': ramp needs {', '.join(needed)} and duration_s")
    current = {pump: vs[-1] for pump, (ts, vs) in tl.schedules.items()}
    total = sum(current.values())
    if total <= 0:
        raise ValueError(f"protocol step '{step.id}': ramp needs running pumps")
    n = max(1, int(round(step.duration_s.value / RAMP_DT_S)))
    dt = step.duration_s.value / n
    for k in range(n):
        tau = p["tau0_min"] + p["alpha"] * (k + 0.5) * dt / 60.0  # ZOH value at interval midpoint
        q_total = p["volume_uL"] / tau
        for pump, q in current.items():
            ts, vs = tl.schedules[pump]
            if ts[-1] == t + k * dt:
                vs[-1] = q / total * q_total
            else:
                ts.append(t + k * dt)
                vs.append(q / total * q_total)
    return t + step.duration_s.value


def initial_flow(f: PaperFeatures, pump_id: str) -> float | None:
    """The pump's flow at t = 0: its first protocol setting, else its component flow rate."""
    tl = timeline(f)
    if pump_id in tl.schedules and tl.schedules[pump_id][0][0] == 0.0:
        return tl.schedules[pump_id][1][0]
    q = f.rig.component(pump_id).flow_rate_uL_min
    return q.value if q.known else None
