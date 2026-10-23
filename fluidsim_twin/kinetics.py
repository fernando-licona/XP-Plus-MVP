"""Species + reaction kinetics for the reactive engines (DESIGN.md §6).

A passive tracer is the single-species, no-reaction case (numerically identical to Phase 0).
Rates use mass-action with optional Arrhenius temperature dependence; everything is in
per-minute to match the TV-RTD time base. This module also holds the reaction *library*
loader (Phase E): a grouped catalogue of seed reactions with kinetics, pickable to load
starting materials A/B onto a run.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

R_GAS = 8.314462618  # J / (mol K)

_LIBRARY_PATH = Path(__file__).with_name("data") / "reactions.toml"


@dataclass(frozen=True)
class RateLaw:
    """``k(T) = A_pre * exp(-Ea / (R T))`` [1/min basis]; ``Ea=0`` -> constant ``A_pre``."""

    A_pre: float
    Ea: float = 0.0           # J/mol

    def k(self, T):
        """``k(T)``; ``T`` may be a scalar or an array (per-axial-station) -> k has the same shape."""
        if self.Ea == 0.0:
            return self.A_pre
        return self.A_pre * np.exp(-self.Ea / (R_GAS * np.maximum(T, 1e-9)))


@dataclass(frozen=True)
class Reaction:
    """One reaction: stoichiometry (neg reactant / pos product), kinetic orders, rate law."""

    stoich: dict[str, float]
    orders: dict[str, float]
    rate: RateLaw


@dataclass
class ReactionNetwork:
    species: list[str]                       # ordered; row order of the concentration vector
    reactions: list[Reaction] = field(default_factory=list)

    def index(self) -> dict[str, int]:
        return {s: i for i, s in enumerate(self.species)}

    def rate_vector(self, C: NDArray, T) -> NDArray:
        """Net formation rate dC/dt for each species [conc/min]. ``C`` is (n_species, ...). ``T`` is a scalar
        OR a per-axial-station array (shape == first spatial axis of ``C``) for an axial temperature gradient
        (e.g. the ramp reactor's left->right profile), in which case ``k(T)`` broadcasts along that axis."""
        idx = self.index()
        dC = np.zeros_like(C, dtype=float)
        spatial = C.shape[1:] if C.ndim > 1 else ()
        for rxn in self.reactions:
            k = rxn.rate.k(T)
            if spatial:
                if np.ndim(k) > 0:                       # axial-varying T: k is (n_axial,) -> (n_axial,1,..)
                    kk = np.asarray(k, float).reshape((-1,) + (1,) * (len(spatial) - 1))
                    r = np.broadcast_to(kk, spatial).astype(float).copy()
                else:
                    r = np.full(spatial, float(k))
            else:
                r = float(k)
            for sp, o in rxn.orders.items():
                r = r * np.maximum(C[idx[sp]], 0.0) ** o
            for sp, nu in rxn.stoich.items():
                dC[idx[sp]] += nu * r
        return dC


def network_from_run(run) -> ReactionNetwork | None:
    """Build a ReactionNetwork from a RunDoc's species + reactions (or None if passive)."""
    species = [s.name for s in run.species]
    if not run.reactions:
        return None
    rxns = []
    for r in run.reactions:
        rate = RateLaw(A_pre=float(r["A_pre"]), Ea=float(r.get("Ea", 0.0)))
        stoich = {k: float(v) for k, v in r["stoich"].items()}
        orders = r.get("orders") or {k: abs(v) for k, v in stoich.items() if v < 0}
        rxns.append(Reaction(stoich=stoich, orders={k: float(v) for k, v in orders.items()},
                             rate=rate))
    return ReactionNetwork(species=species, reactions=rxns)


# ----------------------------------------------------------------- reaction library (Phase E)
@dataclass(frozen=True)
class ReactionEntry:
    """One catalogued reaction: species roles + kinetics, ready to apply to a run."""

    id: str
    name: str
    group: str
    species: list[str]
    optical: str
    stoich: dict[str, float]
    orders: dict[str, float]
    A_pre: float
    Ea: float = 0.0
    reactant_A: str | None = None
    reactant_B: str | None = None
    note: str = ""

    def reaction_dict(self) -> dict:
        """The RunDoc.reactions entry (consumed by :func:`network_from_run`)."""
        return {"stoich": dict(self.stoich), "orders": dict(self.orders),
                "A_pre": self.A_pre, "Ea": self.Ea}


def load_reaction_library(path: str | Path | None = None) -> list[ReactionEntry]:
    """Load the reaction catalogue (seed TOML), returned as ordered :class:`ReactionEntry`s."""
    p = Path(path) if path is not None else _LIBRARY_PATH
    with open(p, "rb") as fh:
        doc = tomllib.load(fh)
    entries = []
    for r in doc.get("reaction", []):
        stoich = {k: float(v) for k, v in r["stoich"].items()}
        orders = {k: float(v) for k, v in (r.get("orders")
                  or {k: abs(v) for k, v in stoich.items() if v < 0}).items()}
        entries.append(ReactionEntry(
            id=r["id"], name=r["name"], group=r["group"], species=list(r["species"]),
            optical=r["optical"], stoich=stoich, orders=orders,
            A_pre=float(r["A_pre"]), Ea=float(r.get("Ea", 0.0)),
            reactant_A=r.get("reactant_A"), reactant_B=r.get("reactant_B"),
            note=r.get("note", "")))
    return entries


def group_reactions(entries: list[ReactionEntry]) -> dict[str, list[ReactionEntry]]:
    """Group catalogue entries by their ``group`` label (insertion-ordered)."""
    out: dict[str, list[ReactionEntry]] = {}
    for e in entries:
        out.setdefault(e.group, []).append(e)
    return out


def apply_reaction(run, entry: ReactionEntry, *, source_A: str, source_B: str | None = None):
    """Return a copy of ``run`` set up to simulate ``entry``: species, reaction, feeds, fidelity.

    ``source_A``/``source_B`` are the source node ids that load reactant A / reactant B. A
    single-reactant entry (no ``reactant_B``) needs only ``source_A``. The product is set as
    the optical species so the absorbance trace tracks conversion.
    """
    from .schema import ObservationDoc, SpeciesDoc       # local import: avoid cycle at import

    species = [SpeciesDoc(name=s, is_optical=(s == entry.optical)) for s in entry.species]
    feeds = {source_A: {entry.reactant_A or entry.species[0]: 1.0}}
    if entry.reactant_B is not None:
        if source_B is None:
            raise ValueError(f"reaction {entry.id!r} needs a second source for "
                             f"reactant {entry.reactant_B!r}")
        feeds[source_B] = {entry.reactant_B: 1.0}
    # Respect the actual temperature: the run's own setpoint (and each reactor's per-node
    # temperature) governs the kinetics. At room temperature a catalogued reaction may show
    # little or no conversion -- that is physically honest, not a bug.
    return run.model_copy(update={
        "species": species,
        "reactions": [entry.reaction_dict()],
        "feeds": feeds,
        "fidelity": "reactive_pde",
        "observation": ObservationDoc(A_full=run.observation.A_full, offset=run.observation.offset),
    })
