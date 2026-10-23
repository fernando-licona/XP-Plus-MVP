"""What the XP Plus app can run: experiment presets and calls into the pipeline (no GUI code)."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from ..extraction import FixtureExtractor
from ..physical import RecordedRunner
from ..pipeline import run_pipeline
from ..schema import ReproStandard, Resolution
from ..twin import GateReport, TwinOptions, run_gate

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
LOGO = ROOT / "assets" / "logo_1.jpg"

# One entry per runnable experiment; options mirror the commands in examples/RESULTS.md.
PRESETS = [
    {"id": "dfe_gp", "label": "CdSe DFE + paper's GP", "dir": "dfe_gp", "black_box": "cdse_gp",
     "backend": "botorch_legacy"},
    {"id": "dfe_rtd_9", "label": "RTD tracer, tau = 9 min", "dir": "dfe_rtd/tau_9min", "bodenstein": 216.5},
    {"id": "dfe_rtd_05", "label": "RTD tracer, tau = 0.5 min", "dir": "dfe_rtd/tau_0p5min", "bodenstein": 301.8},
    {"id": "toy", "label": "Toy tracer paper (synthetic)", "dir": "toy_flow_paper", "observations": "observations.json"},
]


def available_presets() -> list[dict]:
    return [p for p in PRESETS if (EXAMPLES / p["dir"] / "extraction.json").exists()]


def load(preset: dict):
    d = EXAMPLES / preset["dir"]
    extraction = FixtureExtractor().extract(d / "extraction.json")
    path = d / "resolutions.json"
    resolutions = TypeAdapter(list[Resolution]).validate_json(path.read_bytes()) if path.exists() else []
    return d, extraction, resolutions


def gate(preset: dict) -> tuple[object, GateReport]:
    """The paper as written: extraction gaps plus the completeness gate."""
    _, extraction, _ = load(preset)
    return extraction, run_gate(extraction.features)


def run(preset: dict, *, apply_resolutions=True, black_box=True, backend=None,
        paper_bodenstein=False, reactor_only=False) -> ReproStandard:
    d, extraction, resolutions = load(preset)
    options = TwinOptions(
        black_box=preset.get("black_box") if black_box else None,
        black_box_backend=backend or preset.get("backend", "botorch"),
        bodenstein=preset.get("bodenstein") if paper_bodenstein else None,
        connection_holdup=not reactor_only,
    )
    physical = RecordedRunner(d / preset["observations"]) if preset.get("observations") else None
    return run_pipeline(extraction, resolutions=resolutions if apply_resolutions else [], physical=physical,
                        twin_options=options, model_backend=options.black_box_backend)
