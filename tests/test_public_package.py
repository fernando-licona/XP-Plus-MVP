"""Distribution guarantees specific to the self-contained computational MVP."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_imports_are_bundled():
    import xp_plus, fluidsim_twin, m6flow
    for module in (xp_plus, fluidsim_twin, m6flow):
        assert Path(module.__file__).resolve().is_relative_to(ROOT)


def test_only_qualified_export_engines_are_advertised():
    from fluidsim_twin.engines import ENGINES
    from fluidsim_twin.service import TwinService
    assert set(ENGINES) == {'analytical_rtd', 'black_box'}
    with pytest.raises(ValueError, match='unknown fidelity'):
        TwinService._engine('reactive_pde')


def test_local_api_can_inspect_and_gate_examples_without_flowlab():
    from xp_plus.app import api
    items = api.experiments()
    assert {'toy', 'dfe_rtd_9', 'dfe_rtd_05', 'dfe_gp'} == {p['id'] for p in items}
    report = api.gate('dfe_rtd_9')
    assert not report['passed']
    assert sum(g['blocking'] and g['status']=='open' for g in report['gaps']) >= 4


def test_no_hardware_client_or_private_submodule_in_export():
    import xp_plus.physical as physical
    assert not hasattr(physical, 'FlowLabRunner')
    assert not (ROOT/'FlowLab-Automation').exists()
    assert not (ROOT/'.gitmodules').exists()
    assert not (ROOT/'xp_plus/app/lab_edge.py').exists()
