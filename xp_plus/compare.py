"""Stage 4: paper claims vs twin predictions vs physical observations.

Verdict rules mirror FlowLab's verifier (backend/verifier/compare.py) so the two agree:
relative error <= 10% is a match, <= 25% partial, else miss; '~' widens to 25%; '>'/'<'
pass when the inequality holds; no comparable value is missing_data.
"""
from __future__ import annotations

from typing import Optional

from .schema import (
    Claim, ComputationalRecord, OverallVerdict, PhysicalRecord, Quantity, ResultRow, TwinRecord, Verdict,
)
from .units import convert

MATCH_TOL = 0.10
PARTIAL_TOL = 0.25
SYNONYMS = {
    "tau": "residence_time", "residence time": "residence_time", "t_res": "residence_time",
    "t_avg": "mean_residence_time", "tavg": "mean_residence_time",
    "bo": "bodenstein_number", "bodenstein": "bodenstein_number",
}


def _norm(metric: str) -> str:
    m = metric.strip().lower()
    return SYNONYMS.get(m, m.replace(" ", "_"))


def claim_key(claim: Claim) -> str:
    """Key for a prediction made specifically for one claim (e.g. at its `at` condition)."""
    return f"claim:{claim.id}"


def _lookup(values: dict[str, Quantity], claim: Claim) -> Optional[float]:
    q = values.get(claim_key(claim)) or {_norm(k): v for k, v in values.items()}.get(_norm(claim.metric))
    return None if q is None else convert(q.value, q.unit, claim.unit)


def verdict(claim: Claim, observed: Optional[float]) -> Verdict:
    if observed is None or not isinstance(claim.value, float):
        return "missing_data"
    if claim.qualifier == ">":
        return "match" if observed > claim.value else "miss"
    if claim.qualifier == "<":
        return "match" if observed < claim.value else "miss"
    if claim.tolerance is not None:
        err = abs(observed - claim.value)
        return "match" if err <= claim.tolerance else "partial" if err <= 2.5 * claim.tolerance else "miss"
    tol = PARTIAL_TOL if claim.qualifier == "~" else MATCH_TOL
    err = abs(observed - claim.value) / abs(claim.value) if claim.value else abs(observed)
    return "match" if err <= tol else "partial" if err <= PARTIAL_TOL else "miss"


def compare(claims: list[Claim], twin: Optional[TwinRecord], physical: Optional[PhysicalRecord],
            computational: Optional[list[ComputationalRecord]] = None) -> list[ResultRow]:
    comp_metrics = {k: v for rec in (computational or []) for k, v in rec.metrics.items()}
    rows = []
    for c in claims:
        t = _lookup(twin.predictions, c) if twin else None
        p = _lookup(physical.observations, c) if physical else None
        m = _lookup(comp_metrics, c) if comp_metrics else None
        rows.append(ResultRow(claim_id=c.id, metric=c.metric, unit=c.unit, paper=c.value,
                              twin=t, physical=p, computational=m, twin_verdict=verdict(c, t),
                              physical_verdict=verdict(c, p), computational_verdict=verdict(c, m)))
    return rows


def overall(rows: list[ResultRow], gate_passed: bool) -> OverallVerdict:
    """Reproduction is judged on the physical run; the twin alone cannot reproduce a claim."""
    judged = [r.physical_verdict for r in rows if r.physical_verdict != "missing_data"]
    if not gate_passed or not judged:
        return "insufficient_data"
    if all(v == "match" for v in judged):
        return "reproduced"
    if all(v == "miss" for v in judged):
        return "not_reproduced"
    return "partially_reproduced"
