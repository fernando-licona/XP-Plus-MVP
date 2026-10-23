"""The completeness gate (SCOPE.md §3.2): can the paper's experiment be built at all?

    1. structural   can the rig be connected end to end?
    2. parametric   does every component have the values the twin needs?
    3. consistency  do the values agree with each other?

The LLM suggests gaps; the gate proves them. Danamic's own validation does not catch a
disconnected rig, so the structural checks here are the only ones that do.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..protocol import initial_flow
from ..schema import Gap, GapSource, PaperFeatures
from ..units import convert

# kind -> requirement groups. Each group is satisfied by any one alternative; an alternative
# is a tuple of fields that must all be known.
BLOCKING: dict[str, list[list[tuple[str, ...]]]] = {
    "pump": [[("flow_rate_uL_min",)]],
    "mixer": [[("volume_uL",), ("inner_diameter_mm", "length_mm")]],
    "tubing": [[("volume_uL",), ("inner_diameter_mm", "length_mm")]],
    "reactor": [[("volume_uL",), ("inner_diameter_mm", "length_mm")], [("temperature_C",)]],
}
# Metadata that matters for reproducibility but that the twin can run without.
NON_BLOCKING: dict[str, list[str]] = {
    "pump": ["manufacturer", "model"],
    "tubing": ["material"],
    "reactor": ["material"],
    "detector": ["path_length_mm"],
}
CONSISTENCY_TOL = 0.10
SINKS = ("detector", "collection")


@dataclass
class GateReport:
    gaps: list[Gap] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(g.blocking and g.status == "open" for g in self.gaps)

    def by_check(self, detected_by: GapSource) -> list[Gap]:
        return [g for g in self.gaps if g.detected_by == detected_by]


def _gap(detected_by: GapSource, target: str, description: str, blocking: bool = True) -> Gap:
    return Gap(id=f"{detected_by}:{target}", target=target, description=description,
               detected_by=detected_by, blocking=blocking)


def check_structural(f: PaperFeatures) -> list[Gap]:
    rig, gaps = f.rig, []
    ids = {c.id for c in rig.components}
    for e in rig.connections:
        for end in (e.src, e.dst):
            if end not in ids:
                gaps.append(_gap("gate_structural", f"rig.connections.{e.key}",
                                 f"connection {e.key} references unknown component '{end}'"))
    connected = {e.src for e in rig.connections} | {e.dst for e in rig.connections}
    for c in rig.components:
        if c.id not in connected:
            gaps.append(_gap("gate_structural", f"rig.components.{c.id}",
                             f"{c.kind} '{c.id}' is not connected to anything"))
    if not rig.of_kind("pump"):
        gaps.append(_gap("gate_structural", "rig.components", "the rig has no pump"))
    if not rig.of_kind("detector"):
        gaps.append(_gap("gate_structural", "rig.components", "the rig has no detector"))

    sink_ids = {c.id for c in rig.of_kind(*SINKS)}
    for pump in rig.of_kind("pump"):
        seen, stack = set(), [pump.id]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(rig.downstream(node))
        if not seen & sink_ids:
            gaps.append(_gap("gate_structural", f"rig.components.{pump.id}",
                             f"pump '{pump.id}' has no path to a detector or collection"))

    for m in f.measurements:
        if m.instrument not in ids or rig.component(m.instrument).kind != "detector":
            gaps.append(_gap("gate_structural", f"measurements.{m.id}",
                             f"measurement '{m.id}' names '{m.instrument}', which is not a detector"))
    return gaps


def check_parametric(f: PaperFeatures) -> list[Gap]:
    gaps = []
    for step in f.protocol:
        if step.action == "wait" and not step.duration_s.known:
            gaps.append(_gap("gate_parametric", f"protocol.{step.id}.duration_s",
                             f"protocol step '{step.id}' ({step.description}): duration not reported"))
        q = step.parameters.get("flow_rate_uL_min")
        if step.action == "set_flow_rate" and (q is None or not q.known):
            gaps.append(_gap("gate_parametric", f"protocol.{step.id}.parameters.flow_rate_uL_min",
                             f"protocol step '{step.id}' ({step.description}): flow rate not reported"))
        if step.action == "residence_time_ramp":
            for k in ("tau0_min", "alpha", "volume_uL"):
                if k not in step.parameters or not step.parameters[k].known:
                    gaps.append(_gap("gate_parametric", f"protocol.{step.id}.parameters.{k}",
                                     f"protocol step '{step.id}' ({step.description}): {k} not reported"))
            if not step.duration_s.known:
                gaps.append(_gap("gate_parametric", f"protocol.{step.id}.duration_s",
                                 f"protocol step '{step.id}' ({step.description}): duration not reported"))
    scheduled = {s.component for s in f.protocol if s.action == "set_flow_rate"}

    for c in f.rig.components:
        for group in BLOCKING.get(c.kind, []):
            if c.kind == "pump" and c.id in scheduled:
                continue  # the protocol sets this pump's flow
            if any(all(getattr(c, fld).known for fld in alt) for alt in group):
                continue
            # One gap per unmet requirement, targeted at the alternative closest to complete
            # (fewest unknowns, then most knowns): a coil with a length is missing its ID.
            def score(alt):
                unknown = [fld for fld in alt if not getattr(c, fld).known]
                return (len(unknown), -(len(alt) - len(unknown)))
            best = min(group, key=score)
            fld = next(fld for fld in best if not getattr(c, fld).known)
            options = " or ".join("+".join(alt) for alt in group)
            gaps.append(_gap("gate_parametric", f"rig.components.{c.id}.{fld}",
                             f"{c.kind} '{c.id}' needs {options}; '{fld}' is not reported"))
        for fld in NON_BLOCKING.get(c.kind, []):
            if not getattr(c, fld).known:
                gaps.append(_gap("gate_parametric", f"rig.components.{c.id}.{fld}",
                                 f"{c.kind} '{c.id}': {fld} not reported", blocking=False))
    for e in f.rig.connections:
        if e.direct:
            continue
        unknown = [fld for fld in ("inner_diameter_mm", "length_mm") if not getattr(e, fld).known]
        if unknown:
            gaps.append(_gap("gate_parametric", f"rig.connections.{e.key}",
                             f"tubing {e.key}: {' and '.join(unknown)} not reported "
                             "(twin assumes no holdup)", blocking=False))

    # Every measured species must be fed from somewhere at a known concentration.
    reservoirs = f.rig.of_kind("reservoir")
    for m in f.measurements:
        if not m.species:
            continue
        holders = [r for r in reservoirs if m.species in r.contents]
        if not holders:
            gaps.append(_gap("gate_parametric", f"rig.components.*.contents.{m.species}",
                             f"no reservoir is reported to contain measured species '{m.species}'"))
        for r in holders:
            if not r.contents[m.species].known:
                gaps.append(_gap("gate_parametric", f"rig.components.{r.id}.contents.{m.species}",
                                 f"concentration of '{m.species}' in '{r.id}' not reported"))
    return gaps


def reactor_residence_time_s(f: PaperFeatures) -> float | None:
    """Reactor volume / total pump flow. Uses reactors, else tubing segments."""
    parts = f.rig.of_kind("reactor") or f.rig.of_kind("tubing")
    vols = [c.volume_estimate_uL() for c in parts]
    try:
        flows = [initial_flow(f, p.id) for p in f.rig.of_kind("pump")]
    except ValueError:  # incomplete protocol; reported as its own gap
        return None
    if not parts or None in vols or not flows or None in flows or sum(flows) <= 0:
        return None
    return sum(vols) / sum(flows) * 60.0


def check_consistency(f: PaperFeatures) -> list[Gap]:
    gaps = []
    for c in f.rig.components:
        tube = c.tube_volume_uL()
        if tube and c.volume_uL.known and abs(c.volume_uL.value - tube) > CONSISTENCY_TOL * tube:
            gaps.append(_gap("gate_consistency", f"rig.components.{c.id}.volume_uL",
                             f"'{c.id}' volume {c.volume_uL.value:.0f} uL disagrees with "
                             f"ID x length = {tube:.0f} uL", blocking=False))
    tau = reactor_residence_time_s(f)
    for claim in f.claims:
        if claim.metric != "residence_time" or tau is None or not isinstance(claim.value, float):
            continue
        tau_claim = convert(tau, "s", claim.unit)
        if tau_claim is not None and abs(tau_claim - claim.value) > CONSISTENCY_TOL * claim.value:
            gaps.append(_gap("gate_consistency", f"claims.{claim.id}",
                             f"stated residence time {claim.value} {claim.unit} disagrees with "
                             f"volume / flow = {tau_claim:.3g} {claim.unit}", blocking=False))
    return gaps


MODEL_BLOCKING = {  # the model cannot be rebuilt without these
    "gaussian_process": ["kernel"],
    "neural_network": ["architecture", "activation", "optimizer", "learning_rate", "epochs"],
    "other": [],
}
MODEL_NON_BLOCKING = {  # defaults can stand in, but the rebuild may differ from the paper's
    "gaussian_process": ["library", "library_version", "mean_function", "likelihood", "priors",
                         "output_transform", "hyperparameter_fitting", "metric_definitions", "seeds"],
    "neural_network": ["library", "library_version", "batch_size", "initialization", "regularization",
                       "metric_definitions", "seeds"],
    "other": ["library", "library_version"],
}


def check_model(f: PaperFeatures) -> list[Gap]:
    """Can each data-driven model the paper uses be rebuilt from what the paper provides?"""
    gaps = []
    ids = {c.id for c in f.rig.components}
    for m in f.models:
        base = f"models.{m.id}"
        if not m.inputs or not m.outputs:
            gaps.append(_gap("gate_model", base, f"model '{m.id}': inputs or outputs not defined"))
        if not m.training_data.known:
            gaps.append(_gap("gate_model", f"{base}.training_data",
                             f"model '{m.id}': training data not available"))
        for fld in MODEL_BLOCKING[m.family]:
            if not getattr(m, fld).known:
                gaps.append(_gap("gate_model", f"{base}.{fld}", f"model '{m.id}': {fld} not reported"))
        for fld in MODEL_NON_BLOCKING[m.family]:
            if not getattr(m, fld).known:
                gaps.append(_gap("gate_model", f"{base}.{fld}",
                                 f"model '{m.id}': {fld} not reported (defaults assumed)", blocking=False))
        if m.validation_protocol is None:
            gaps.append(_gap("gate_model", f"{base}.validation_protocol",
                             f"model '{m.id}': validation protocol not specified", blocking=False))
        # Paths follow the schema (models.<id>.inputs.<name>.<field>) so resolutions can target them.
        for group, items in (("inputs", m.inputs), ("outputs", m.outputs)):
            for io in items:
                path = f"{base}.{group}.{io.name}"
                for fld in ("low", "high"):
                    if not getattr(io, fld).known:
                        gaps.append(_gap("gate_model", f"{path}.{fld}",
                                         f"model '{m.id}': normalization of '{io.name}' not reported"))
                if not io.definition.known:
                    gaps.append(_gap("gate_model", f"{path}.definition",
                                     f"model '{m.id}': '{io.name}' is not defined", blocking=False))
        for i in m.inputs:
            path = f"{base}.inputs.{i.name}"
            refs = ([i.node] if i.kind in ("residence_time", "temperature") else []) + i.numerator + i.denominator
            for r in refs:
                if r not in ids:
                    gaps.append(_gap("gate_model", path,
                                     f"model '{m.id}': input '{i.name}' refers to unknown component '{r}'"))
            if i.kind == "constant" and not i.value.known:
                gaps.append(_gap("gate_model", f"{path}.value",
                                 f"model '{m.id}': constant input '{i.name}' has no value"))
    return gaps


def run_gate(f: PaperFeatures) -> GateReport:
    """Structural problems make parametric results meaningless, so stop there if any."""
    structural = check_structural(f)
    if structural:
        return GateReport(structural)
    return GateReport(check_parametric(f) + check_consistency(f) + check_model(f))
