import pytest

from xp_plus.resolve import apply_resolutions
from xp_plus.schema import Resolution


def _res(target, value, provenance="measured"):
    return Resolution(target=target, value=value, provenance=provenance)


def test_resolutions_land_on_components_connections_and_environment(toy_extraction):
    f = apply_resolutions(toy_extraction.features, [
        _res("rig.components.coil.inner_diameter_mm", 0.762),
        _res("rig.connections.coil->cell.length_mm", 300.0),
        _res("rig.components.resB.contents.solvent", 1.0, "assumed"),
        _res("environment.relative_humidity_pct", 45.0),
    ])
    assert f.rig.component("coil").inner_diameter_mm.value == 0.762
    assert f.rig.component("coil").inner_diameter_mm.provenance == "measured"
    assert next(c for c in f.rig.connections if c.key == "coil->cell").length_mm.value == 300.0
    assert f.rig.component("resB").contents["solvent"].provenance == "assumed"
    assert f.environment.relative_humidity_pct.value == 45.0


def test_original_is_not_mutated(toy_extraction):
    apply_resolutions(toy_extraction.features, [_res("rig.components.coil.inner_diameter_mm", 0.762)])
    assert not toy_extraction.features.rig.component("coil").inner_diameter_mm.known


@pytest.mark.parametrize("target", ["rig.components.nope.length_mm", "rig.components.coil.kind"])
def test_bad_targets_raise(toy_extraction, target):
    with pytest.raises(KeyError):
        apply_resolutions(toy_extraction.features, [_res(target, 1.0)])
