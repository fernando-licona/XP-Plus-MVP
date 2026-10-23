"""Black-box option: model cards, the model gate, computational reproduction, and the twin."""
import pytest
from pydantic import TypeAdapter

from xp_plus.extraction import FixtureExtractor
from xp_plus.protocol import timeline
from xp_plus.resolve import apply_resolutions
from xp_plus.schema import ModelCard, ModelInput, Resolution, Tagged
from xp_plus.twin import run_gate
from xp_plus.twin.gate import check_model
from tests.conftest import ROOT

GP = ROOT / "examples" / "dfe_gp"


@pytest.fixture
def gp_extraction():
    return FixtureExtractor().extract(GP / "extraction.json")


@pytest.fixture
def gp_resolutions():
    return TypeAdapter(list[Resolution]).validate_json((GP / "resolutions.json").read_bytes())


def test_paper_gp_is_specified_except_version_dependent_defaults(gp_extraction):
    gaps = [g for g in run_gate(gp_extraction.features).gaps if g.detected_by == "gate_model"]
    assert not any(g.blocking for g in gaps)
    assert {g.target for g in gaps} == {
        "models.cdse_gp.library_version", "models.cdse_gp.priors", "models.cdse_gp.output_transform"}


def test_model_gate_blocks_an_unbuildable_model(gp_extraction):
    card = gp_extraction.features.models[0]
    card.kernel, card.training_data = Tagged[str](), Tagged[str]()
    card.inputs.append(ModelInput(name="mystery", kind="flow_fraction", numerator=["nope"]))
    blocking = {g.target for g in check_model(gp_extraction.features) if g.blocking}
    assert {"models.cdse_gp.kernel", "models.cdse_gp.training_data", "models.cdse_gp.inputs.mystery",
            "models.cdse_gp.inputs.mystery.low", "models.cdse_gp.inputs.mystery.high"} <= blocking


def test_model_gap_targets_are_resolvable_paths(gp_extraction):
    from xp_plus.resolve import apply_resolution
    card = gp_extraction.features.models[0]
    card.inputs[0].low = Tagged[float]()
    [gap] = [g for g in check_model(gp_extraction.features) if g.target.endswith(".low")]
    apply_resolution(gp_extraction.features, Resolution(target=gap.target, value=1 / 6, provenance="inferred",
                                                        note="SI Eq. 4"))
    assert card.inputs[0].low.value == 1 / 6


def test_neural_network_needs_its_training_recipe():
    from xp_plus.schema import PaperFeatures, PaperRef
    f = PaperFeatures(paper=PaperRef(title="t"), models=[ModelCard(id="nn", family="neural_network")])
    blocking = {g.target.split(".")[-1] for g in check_model(f) if g.blocking}
    assert {"architecture", "activation", "optimizer", "learning_rate", "epochs"} <= blocking


def test_comparison_findings_stay_open_until_reviewed(gp_extraction, gp_resolutions):
    from xp_plus.pipeline import _merge_gaps
    gaps = _merge_gaps(gp_extraction.gaps, [], gp_resolutions, original_features=gp_extraction.features,
                       features=apply_resolutions(gp_extraction.features, gp_resolutions))
    assert {g.id: g.status for g in gaps}["comparison:claims.cv_r2_em"] == "open"


def test_ramp_keeps_ratios_and_follows_eq1(gp_extraction, gp_resolutions):
    tl = timeline(apply_resolutions(gp_extraction.features, gp_resolutions))
    pumps = ("pump_cd", "pump_se", "pump_cd_ode", "pump_se_ode")
    t0 = tl.step_times["ramp"]
    k = next(i for i, t in enumerate(tl.schedules["pump_cd"][0]) if t >= t0 + 600)  # 10 min into the ramp
    total = sum(tl.schedules[p][1][k] for p in pumps)
    t_mid = tl.schedules["pump_cd"][0][k] + 1.0  # ZOH value is taken at the interval midpoint
    assert total == pytest.approx(1113 / (1 + 0.6 * (t_mid - t0) / 60), rel=1e-3)
    assert tl.schedules["pump_cd"][1][k] / total == pytest.approx(245.77 / 1113.0, rel=1e-3)


botorch = pytest.importorskip("botorch", reason="BoTorch not installed")


def _card(gp_extraction):
    card = gp_extraction.features.models[0]
    try:
        from xp_plus.blackbox.data import training_data_path
        training_data_path(card)
    except Exception as exc:  # offline and not cached
        pytest.skip(f"training data unavailable: {exc}")
    return card


def test_rebuilt_gp_reproduces_reported_r2_with_labels_exchanged(gp_extraction):
    from xp_plus.blackbox import reproduce_validation
    m = reproduce_validation(_card(gp_extraction), "botorch_legacy").metrics
    assert m["cv_r2_emission_wavelength"].value == pytest.approx(0.988, abs=0.005)  # paper: FWHM 0.988
    assert m["cv_r2_fwhm"].value == pytest.approx(0.967, abs=0.005)                 # paper: lambda_em 0.967


pytest.importorskip("fluidsim_twin", reason="Danamic Simulations not installed")


def test_black_box_twin_predicts_the_steady_state_equivalents(gp_extraction, gp_resolutions):
    from xp_plus.pipeline import run_pipeline
    from xp_plus.twin import TwinOptions
    _card(gp_extraction)
    std = run_pipeline(gp_extraction, resolutions=gp_resolutions, validate_models=False,
                       twin_options=TwinOptions(black_box="cdse_gp"))
    assert std.twin.fidelity == "black_box"
    rows = {r.claim_id: r for r in std.results}
    for tau in range(1, 8):
        assert rows[f"ssfe_em_tau{tau}"].twin_verdict == "match"  # within the paper's 4.1 nm RMSE
        assert rows[f"dfe_em_tau{tau}"].twin == pytest.approx(rows[f"dfe_em_tau{tau}"].paper, abs=1.9)
