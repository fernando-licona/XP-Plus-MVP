"""The first real paper: Delgado-Licona et al. (2025), SI §1 RTD step experiments."""
import pytest
from pydantic import TypeAdapter

from xp_plus.extraction import FixtureExtractor
from xp_plus.pipeline import run_pipeline
from xp_plus.protocol import timeline
from xp_plus.resolve import apply_resolutions
from xp_plus.schema import Resolution
from xp_plus.twin import TwinOptions, run_gate
from tests.conftest import ROOT

DFE = ROOT / "examples" / "dfe_rtd"


def _load(case):
    ex = FixtureExtractor().extract(DFE / case / "extraction.json")
    res = TypeAdapter(list[Resolution]).validate_json((DFE / case / "resolutions.json").read_bytes())
    return ex, res


def test_paper_as_written_is_missing_four_values():
    ex, _ = _load("tau_9min")
    blocking = {g.target for g in run_gate(ex.features).gaps if g.blocking}
    assert blocking == {
        "protocol.equilibrate.duration_s", "protocol.record.duration_s",
        "rig.components.tee.volume_uL", "rig.components.res_dye.contents.sudan_blue_ii",
    }


def test_protocol_timeline_is_the_ratio_step():
    ex, res = _load("tau_9min")
    tl = timeline(apply_resolutions(ex.features, res))
    assert tl.step_times["step_ode"] == pytest.approx(3 * 9 * 60)  # after 3 reactor volumes
    ts, vs = tl.schedules["pump_dye"]
    assert vs[1] == pytest.approx(3 * vs[0], rel=1e-3)  # 3:1 -> 1:3 at constant total flow
    assert sum(tl.schedules[p][1][0] for p in ("pump_dye", "pump_ode")) == pytest.approx(1113 / 9, rel=1e-3)


pytest.importorskip("fluidsim_twin", reason="Danamic Simulations not installed")


def _results(case, **options):
    ex, res = _load(case)
    std = run_pipeline(ex, resolutions=res, twin_options=TwinOptions(**options))
    return {r.claim_id: r for r in std.results}, std


def test_detector_timing_includes_the_228_uL_line():
    """Timed at the detector, the 50 cm line adds ~1.8 min: t_avg ~10.9 min, not 8.7."""
    rows, std = _results("tau_9min")
    assert std.verdict == "insufficient_data"  # no physical run yet
    assert rows["tau_nominal"].twin_verdict == "match"
    assert rows["t_avg"].twin == pytest.approx(9.0 + 228 / (1113 / 9), rel=0.02)


@pytest.mark.parametrize("case, bo", [("tau_9min", 216.5), ("tau_0p5min", 301.8)])
def test_reactor_only_twin_with_paper_bo_recovers_the_papers_fit(case, bo):
    rows, _ = _results(case, bodenstein=bo, connection_holdup=False)
    assert rows["t_avg"].twin_verdict == "match"
    assert rows["bo"].twin == pytest.approx(bo, rel=0.03)
