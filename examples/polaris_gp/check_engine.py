"""Wire a rebuilt Junbin GP through Danamic's real engine on synthetic transport.

This does NOT reproduce the paper's platform, segmentation or chemistry.
Run check.py first. No FlowLab runtime or hardware is used.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--card', type=Path, default=ROOT/'.cache/xp_plus/polaris-check/probe-model-card.json')
    p.add_argument('--out', type=Path, default=ROOT/'.cache/xp_plus/polaris-check/engine-result.json')
    args = p.parse_args()
    import numpy as np
    import torch
    from xp_plus.schema import ModelCard
    from xp_plus.blackbox.model import BlackBoxModel
    from fluidsim_twin.schema import PlatformDoc, NodeDoc, PumpSpec, RtdSpec, EdgeDoc, RunDoc, ScheduleDoc, BlackBoxDoc, FeatureDoc
    from fluidsim_twin.service import TwinService
    torch.set_num_threads(1)
    card = ModelCard.model_validate_json(args.card.read_text(encoding='utf-8'))
    physical_inputs = np.array([[i.value.value for i in card.inputs]])
    card.inputs[-1].kind = 'temperature'
    card.inputs[-1].node = 'probe_reactor'
    platform = PlatformDoc(platform_id='synthetic_gp_plumbing_only', nodes=[
        NodeDoc(id='source', type='source', pump=PumpSpec(gain=1., beta=0., theta=0., tau_fast=.001, w_slow=0.)),
        NodeDoc(id='probe_reactor', type='reactor', V=100., rtd=RtdSpec(model='plug'), temperature_K=493.15),
        NodeDoc(id='cell', type='sink', kind='cell')], edges=[EdgeDoc(src='source', dst='probe_reactor'), EdgeDoc(src='probe_reactor', dst='cell')])
    run = RunDoc(run_id='probe', platform_ref=platform.platform_id, grid={'t0': 0., 't_end': 120., 'dt': 1.},
        schedules={'source': ScheduleDoc(t_breaks=[0.], values=[100.])}, fidelity='black_box',
        black_box=BlackBoxDoc(model='xp_plus.blackbox.model:danamic_factory', args={'card_json': card.model_dump_json(), 'backend': 'botorch'},
            features=[FeatureDoc(name=i.name, kind=i.kind, node=i.node, value=i.value.value) for i in card.inputs], outputs=['plqy_proxy']))
    svc = TwinService()
    errors = svc.validate(platform, run)
    assert not errors, errors
    print('Running real black_box engine with Junbin GP on synthetic transport.', flush=True)
    res = svc.simulate(platform, run)
    signal = res.signals['cell:black_box']
    mean, std = np.asarray(signal['cell'])[0], np.asarray(signal['std'])[0]
    expected = float(BlackBoxModel(card, 'botorch').fit().predict(physical_inputs)[0][0, 0])
    assert res.fidelity_used == 'black_box' and np.isnan(mean[0]) and np.isfinite(mean[-1])
    assert abs(mean[-1] - expected) < 1e-10
    result = {'fidelity': res.fidelity_used,
        'scope': 'Engine/model wiring ONLY: one ideal source, assumed 100 uL plug-flow reactor, 100 uL/min, 120 s. Six paper feed inputs constant; temperature bound dynamically. Not the paper rig or a FlowLab Run.',
        'points': len(mean), 'first_finite_time_s': float(np.asarray(res.tg)[np.flatnonzero(np.isfinite(mean))[0]]),
        'mean_proxy_fraction': float(mean[-1]), 'posterior_std_fraction': float(std[-1]),
        'matches_direct_gp_prediction': True, 'no_finite_prediction_at_t0': True,
        'diagnostics': res.diagnostics}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(json.dumps(result, indent=2, default=str), flush=True)


if __name__ == '__main__':
    main()
