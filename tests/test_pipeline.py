import pytest

from xp_plus.physical import RecordedRunner
from xp_plus.pipeline import run_pipeline
from xp_plus.schema import ReproStandard
from tests.conftest import TOY

pytest.importorskip("fluidsim_twin", reason="Danamic Simulations not installed")


def test_paper_as_written_gives_insufficient_data(toy_extraction):
    std = run_pipeline(toy_extraction)
    assert std.verdict == "insufficient_data" and std.twin is None
    assert any(g.blocking and g.status == "open" for g in std.gaps)


def test_resolved_toy_end_to_end(toy_extraction, toy_resolutions, tmp_path):
    std = run_pipeline(toy_extraction, resolutions=toy_resolutions,
                       physical=RecordedRunner(TOY / "observations.json"))
    assert std.verdict == "reproduced"

    # Twin: plug-flow reactor tau vs simulated tracer arrival (mixer + outlet tubing add a little).
    tau = std.twin.predictions["residence_time"].value
    t50 = std.twin.predictions["tracer_t50"].value
    assert tau == pytest.approx(547.2, rel=1e-3)
    assert tau < t50 < 1.1 * tau

    # Gaps report keeps what the paper lacked, with how each was closed.
    gaps = {g.target: g for g in std.gaps}
    coil = gaps["rig.components.coil.inner_diameter_mm"]
    assert coil.status == "resolved" and coil.resolutions[0].provenance == "measured"
    assert gaps["rig.connections.coil->cell"].status == "resolved"
    assert len(gaps["rig.connections.coil->cell"].resolutions) == 2
    assert gaps["rig.connections.mixer->coil"].status == "open"
    assert gaps["environment.relative_humidity_pct"].status == "resolved"

    path = tmp_path / "standard.json"
    std.save(path)
    assert ReproStandard.load(path).verdict == "reproduced"
