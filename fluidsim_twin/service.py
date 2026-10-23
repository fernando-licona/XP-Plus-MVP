"""Danamic facade limited to unchanged build/validate/simulate methods for the public MVP."""
from .build import ResolvedFlowsheet, build_flowsheet
from .engines import ENGINES, AnalyticalRTDEngine
from .engines.base import SimResult
from .schema import PlatformDoc, RunDoc
class TwinService:
    def build_flowsheet(self, platform: PlatformDoc, run: RunDoc) -> ResolvedFlowsheet:
        return build_flowsheet(platform, run)

    def validate(self, platform: PlatformDoc, run: RunDoc) -> list[str]:
        """Return a list of human-readable issues; empty means the run is simulable."""
        issues: list[str] = []
        try:
            resolved = build_flowsheet(platform, run)
        except Exception as exc:  # build errors are user-facing validation failures
            return [f"build: {exc}"]
        engine = self._engine(run.fidelity)
        rep = engine.capabilities(resolved)
        issues.extend(rep.errors)
        return issues

    def simulate(self, platform: PlatformDoc, run: RunDoc, *,
                 progress=None, cancel=None, optical_models=None) -> SimResult:
        resolved = build_flowsheet(platform, run)
        if optical_models is not None:                 # data-driven: use calibrated per-species spectra
            resolved.optical_models = optical_models
        engine = self._engine(run.fidelity)
        return engine.run(resolved, progress=progress, cancel=cancel)

    @staticmethod
    def _engine(fidelity: str):
        cls = ENGINES.get(fidelity)
        if cls is None:
            raise ValueError(f"unknown fidelity {fidelity!r}; have {sorted(ENGINES)}")
        return cls()
