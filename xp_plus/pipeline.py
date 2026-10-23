"""Stage 5: run every stage and assemble the Reproducibility Standard.

    extract -> gate (on the paper as written) -> resolve -> gate again -> twin -> physical
            -> compare -> ReproStandard

Gating the paper *as written* first is what makes the gaps report: every gap found there
is kept, and marked resolved if a resolution (or a later check) closed it.
The iterate loop (SCOPE.md §3.4) is one pass for now: TODO.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Mapping, Optional

from .compare import compare, overall
from .extraction import Extraction
from .physical import PhysicalRunner
from .resolve import _child, apply_resolutions
from .schema import Gap, Iteration, ReproStandard, Resolution, Tagged
from .twin import TwinOptions, predict, run_gate


def _field(features, target):
    try:
        value = features
        for part in target.split("."):
            value = _child(value, part)
        return value
    except (KeyError, AttributeError):
        return None


def _overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def _merge_gaps(found: list[Gap], remaining: list[Gap], resolutions: list[Resolution],
                *, original_features=None, features=None,
                gap_closures: Mapping[str, str] | None = None) -> list[Gap]:
    """Keep extraction omissions open until the exact omission or an explicit review closes it.

    A scalar resolution cannot establish that an entire prefix or a contradiction was
    resolved. Reviewed exports can carry an explicit closure_reason; neither kind of
    closure overrides a remaining blocking deterministic gate at that target.
    """
    closures = dict(gap_closures or {})
    # Only deterministic gate gaps close by themselves (the re-run gate stops reporting them);
    # extraction and comparison findings need the exact value or an explicit review.
    reviewed = lambda gap: not gap.detected_by.startswith("gate_")
    extraction_ids = {g.id for g in found if reviewed(g)}
    if any(key not in extraction_ids or not isinstance(reason, str) or not reason.strip()
           for key, reason in closures.items()):
        raise ValueError("gap_closures must name extraction gaps with a nonempty review reason")
    still_open = {g.id for g in remaining}
    merged: dict[str, Gap] = {}
    for original in found + remaining:
        if original.id in merged:
            continue
        g = original.model_copy(deep=True)
        g.resolutions = [r for r in resolutions
                         if r.target == g.target or r.target.startswith(g.target + ".")]
        if reviewed(g):
            before, after = _field(original_features, g.target), _field(features, g.target)
            blocked = any(r.blocking and r.status == "open" and _overlaps(g.target, r.target)
                          for r in remaining)
            exact_missing = (isinstance(before, Tagged) and not before.known
                             and isinstance(after, Tagged) and after.known
                             and any(r.target == g.target for r in resolutions))
            reason = closures.get(g.id)
            if reason is None and original.status == "resolved" and original.closure_reason and original.closure_reason.strip():
                reason = original.closure_reason
            g.status = "resolved" if not blocked and (exact_missing or reason) else "open"
            g.closure_reason = (reason or "Exact missing field supplied by a provenance-tagged resolution") if g.status == "resolved" else None
        else:
            g.status = "open" if g.id in still_open else "resolved"
        merged[g.id] = g
    return list(merged.values())


def run_pipeline(extraction: Extraction, *, resolutions: Iterable[Resolution] = (),
                 physical: Optional[PhysicalRunner] = None,
                 twin_options: Optional[TwinOptions] = None,
                 reproduced_by: Iterable[str] = (),
                 gap_closures: Mapping[str, str] | None = None,
                 validate_models: bool = True, model_backend: str = "botorch") -> ReproStandard:
    resolutions = list(resolutions)
    paper_gate = run_gate(extraction.features)
    features = apply_resolutions(extraction.features, resolutions)
    gate = run_gate(features)
    gaps = _merge_gaps(extraction.gaps + paper_gate.gaps, gate.gaps, resolutions,
                       original_features=extraction.features, features=features, gap_closures=gap_closures)
    runnable = gate.passed and not any(g.blocking and g.status == "open" for g in gaps)

    twin = predict(features, twin_options) if runnable else None
    phys = physical.run(features) if physical is not None and runnable else None
    # Computational reproduction: re-run each paper model's own validation (no hardware needed).
    computational = []
    if runnable and validate_models:
        from .blackbox import reproduce_validation
        computational = [reproduce_validation(m, model_backend) for m in features.models
                         if m.validation_protocol is not None]
    rows = compare(features.claims, twin, phys, computational)

    paper = features.paper
    key = f"{paper.doi or paper.title}|{features.experiment or ''}"
    standard_id = "xpp-" + hashlib.sha256(key.encode()).hexdigest()[:12]
    n_open = sum(g.status == "open" for g in gaps)
    summary = (f"{len(gaps)} gaps found ({n_open} open, {len(resolutions)} resolutions applied); "
               f"gate {'passed' if runnable else 'blocked'}")
    return ReproStandard(standard_id=standard_id, reproduced_by=list(reproduced_by),
                         features=features, twin=twin, physical=phys, computational=computational, results=rows,
                         verdict=overall(rows, runnable), gaps=gaps,
                         iterations=[Iteration(index=0, changes=[r.target for r in resolutions],
                                               summary=summary)])
