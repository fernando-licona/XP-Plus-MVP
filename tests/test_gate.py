from xp_plus.schema import Component, Connection, Tagged
from xp_plus.twin import run_gate


def _blocking_targets(report):
    return {g.target for g in report.gaps if g.blocking}


def test_paper_as_written_is_blocked_on_the_missing_geometry(toy_extraction):
    report = run_gate(toy_extraction.features)
    assert not report.passed
    # One gap per unmet requirement: the coil has a length, so it is missing its ID.
    assert _blocking_targets(report) == {
        "rig.components.coil.inner_diameter_mm",
        "rig.components.mixer.volume_uL",
    }


def test_unreported_tubing_is_a_non_blocking_gap(toy_extraction):
    gaps = {g.target: g for g in run_gate(toy_extraction.features).gaps}
    assert not gaps["rig.connections.mixer->coil"].blocking


def test_resolved_toy_passes(toy_resolved):
    assert run_gate(toy_resolved).passed


def test_disconnected_component_is_structural(toy_resolved):
    toy_resolved.rig.components.append(Component(id="orphan", kind="tubing"))
    report = run_gate(toy_resolved)
    assert not report.passed
    assert [g.target for g in report.by_check("gate_structural")] == ["rig.components.orphan"]


def test_pump_without_path_to_detector_is_structural(toy_resolved):
    rig = toy_resolved.rig
    rig.connections = [c for c in rig.connections if c.key != "pumpB->mixer"]
    rig.components.append(Component(id="dead_end", kind="tubing"))
    rig.connections.append(Connection(src="pumpB", dst="dead_end"))
    targets = {g.target for g in run_gate(toy_resolved).by_check("gate_structural")}
    assert "rig.components.pumpB" in targets


def test_volume_contradicting_geometry_is_a_consistency_gap(toy_resolved):
    coil = toy_resolved.rig.component("coil")
    coil.volume_uL = Tagged[float](value=1000.0, provenance="paper_stated")  # tube is ~4560 uL
    gaps = run_gate(toy_resolved).by_check("gate_consistency")
    # The stated volume is used, so it also contradicts the 10 min residence-time claim.
    assert [g.target for g in gaps] == ["rig.components.coil.volume_uL", "claims.tau"]


def test_residence_time_claim_contradicting_volume_over_flow(toy_resolved):
    toy_resolved.claims[0].value = 20.0  # volume / flow is ~9.1 min
    gaps = run_gate(toy_resolved).by_check("gate_consistency")
    assert [g.target for g in gaps] == ["claims.tau"]
