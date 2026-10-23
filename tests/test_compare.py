import pytest

from xp_plus.compare import compare, overall, verdict
from xp_plus.schema import Claim, PhysicalRecord, Quantity


def _claim(value, qualifier="=", unit="min"):
    return Claim(id="c", metric="residence_time", value=value, unit=unit, qualifier=qualifier)


@pytest.mark.parametrize("observed, qualifier, expected", [
    (10.5, "=", "match"), (11.5, "=", "partial"), (13.0, "=", "miss"),
    (12.0, "~", "match"), (11.0, ">", "match"), (9.0, ">", "miss"), (None, "=", "missing_data"),
])
def test_verdict_rules_mirror_flowlab(observed, qualifier, expected):
    assert verdict(_claim(10.0, qualifier), observed) == expected


def test_units_are_converted_into_the_claims_unit():
    phys = PhysicalRecord(runner="recorded", observations={"tau": Quantity(value=600.0, unit="s")})
    [row] = compare([_claim(10.0)], None, phys)
    assert row.physical == pytest.approx(10.0) and row.physical_verdict == "match"


def test_overall_needs_a_physical_result_and_a_passed_gate():
    phys = PhysicalRecord(runner="recorded", observations={"residence_time": Quantity(value=10.0, unit="min")})
    rows = compare([_claim(10.0)], None, phys)
    assert overall(rows, gate_passed=True) == "reproduced"
    assert overall(rows, gate_passed=False) == "insufficient_data"
    assert overall(compare([_claim(10.0)], None, None), gate_passed=True) == "insufficient_data"
