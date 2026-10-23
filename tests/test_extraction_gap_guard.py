"""Extraction omissions must guard both twin and physical invocation."""
import pytest

from xp_plus.extraction import Extraction
from xp_plus.pipeline import run_pipeline
from xp_plus.schema import Component, Connection, Gap, PaperFeatures, PaperRef, Resolution, Rig, Tagged, TwinRecord


def experiment(*gaps):
    return Extraction(features=PaperFeatures(paper=PaperRef(title="Original synthetic gate example"),
        rig=Rig(components=[Component(id="pump",kind="pump",flow_rate_uL_min=Tagged(value=60.0,provenance="paper_stated",source="Synthetic p1: 60 uL/min")),
                            Component(id="detector",kind="detector")],
                connections=[Connection(src="pump",dst="detector",direct=True)])),gaps=list(gaps))


def missing(target,blocking=True):
    return Gap(id="extraction:"+target,target=target,description="Unreported preparation detail",
               detected_by="extraction",blocking=blocking)


def stub(monkeypatch):
    calls=[]
    monkeypatch.setattr("xp_plus.pipeline.predict",lambda *args: calls.append("twin") or TwinRecord(fidelity="synthetic-test"))
    class Physical:
        def run(self,*args):
            calls.append("physical")
            raise AssertionError("Physical must not run in guard tests")
    return calls,Physical()


def test_open_blocking_extraction_gap_prevents_both_runners(monkeypatch):
    calls,physical=stub(monkeypatch)
    result=run_pipeline(experiment(missing("protocol.equilibration")),physical=physical)
    assert calls == []
    assert result.twin is None and result.physical is None
    assert result.verdict == "insufficient_data"
    assert "gate blocked" in result.iterations[0].summary


def test_one_child_resolution_does_not_close_prefix_gap(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("environment"))
    result=run_pipeline(ex,resolutions=[Resolution(target="environment.ambient_temperature_C",value=20.0,
                                                 provenance="measured",note="Synthetic measured value")])
    assert calls == []
    assert result.gaps[0].status == "open"
    assert result.gaps[0].closure_reason is None


def test_known_value_contradiction_needs_explicit_review(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("rig.components.pump.flow_rate_uL_min"))
    result=run_pipeline(ex,resolutions=[Resolution(target="rig.components.pump.flow_rate_uL_min",value=50.0,
                                                 provenance="assumed",note="Choose a delivery setting")])
    assert calls == []
    assert result.gaps[0].status == "open"


def test_exact_missing_scalar_resolution_closes_only_that_gap(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("environment.ambient_temperature_C"))
    result=run_pipeline(ex,resolutions=[Resolution(target="environment.ambient_temperature_C",value=20.0,
                                                 provenance="measured",note="Synthetic measured value")])
    assert calls == ["twin"]
    assert result.gaps[0].status == "resolved"
    assert result.gaps[0].closure_reason
    assert not ex.features.environment.ambient_temperature_C.known


def test_prefix_closure_is_explicit_and_retained(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("environment"))
    reason="Reviewed complete environmental requirements for this synthetic passive tracer"
    result=run_pipeline(ex,gap_closures={ex.gaps[0].id:reason})
    assert calls == ["twin"]
    assert result.gaps[0].closure_reason == reason
    assert ex.gaps[0].status == "open"


def test_reviewed_export_closure_reason_round_trips(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("environment"))
    ex.gaps[0].status="resolved"
    ex.gaps[0].closure_reason="Explicit synthetic review decision retained by exporter"
    result=run_pipeline(ex)
    assert calls == ["twin"]
    assert result.gaps[0].status == "resolved"


def test_closure_cannot_override_remaining_blocking_gate(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("rig.components.pump.flow_rate_uL_min"))
    ex.features.rig.component("pump").flow_rate_uL_min=Tagged()
    result=run_pipeline(ex,gap_closures={ex.gaps[0].id:"Attempted manual override"})
    assert calls == []
    assert result.gaps[0].status == "open"
    assert result.gaps[0].closure_reason is None


@pytest.mark.parametrize("closures",[{"unknown":"reason"},{"extraction:environment":" "}])
def test_invalid_explicit_closure_is_rejected(closures):
    with pytest.raises(ValueError,match="gap_closures"):
        run_pipeline(experiment(missing("environment")),gap_closures=closures)


def test_whitespace_export_closure_does_not_bypass_guard(monkeypatch):
    calls,_=stub(monkeypatch)
    ex=experiment(missing("environment"))
    ex.gaps[0].status="resolved"
    ex.gaps[0].closure_reason=" "
    result=run_pipeline(ex)
    assert calls == []
    assert result.gaps[0].status == "open"
