from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from xp_plus.extraction import FixtureExtractor
from xp_plus.resolve import apply_resolutions
from xp_plus.schema import Resolution

ROOT = Path(__file__).resolve().parents[1]
TOY = ROOT / "examples" / "toy_flow_paper"


@pytest.fixture
def toy_extraction():
    return FixtureExtractor().extract(TOY / "extraction.json")


@pytest.fixture
def toy_resolutions():
    return TypeAdapter(list[Resolution]).validate_json((TOY / "resolutions.json").read_bytes())


@pytest.fixture
def toy_resolved(toy_extraction, toy_resolutions):
    return apply_resolutions(toy_extraction.features, toy_resolutions)
