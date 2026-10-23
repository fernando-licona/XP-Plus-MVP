import json

import pytest
from pydantic import ValidationError

from xp_plus.schema import PaperRef, PaperFeatures, ReproStandard, Tagged


def test_tagged_missing_iff_no_value():
    assert not Tagged[float]().known
    assert Tagged[float](value=1.0, provenance="measured").known
    with pytest.raises(ValidationError):
        Tagged[float](value=1.0)  # a value needs a provenance
    with pytest.raises(ValidationError):
        Tagged[float](provenance="paper_stated")  # stated, but no value


def test_extraction_fixture_tags_every_value(toy_extraction):
    coil = toy_extraction.features.rig.component("coil")
    assert coil.length_mm.provenance == "paper_stated" and coil.length_mm.source
    assert coil.inner_diameter_mm.provenance == "missing"


def test_standard_roundtrip(tmp_path):
    std = ReproStandard(standard_id="x", features=PaperFeatures(paper=PaperRef(title="t")))
    path = tmp_path / "s.json"
    std.save(path)
    assert ReproStandard.load(path) == std


def test_json_schema_exports():
    schema = json.loads(ReproStandard.json_schema())
    assert {"features", "gaps", "results", "verdict"} <= set(schema["properties"])
