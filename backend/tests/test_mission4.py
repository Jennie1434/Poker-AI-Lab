import asyncio
import json

import pytest

from pokerbench.benchmark import experiment
from pokerbench.cfr import CFRTrainer
from pokerbench.holdem_abstraction import Abstraction, HoldemAbstractGame, export_policy
import pokerbench.mission4 as m4


def test_preregistered_plan_uses_new_seeds_and_fixed_sizes():
    plan = list(m4.jobs())
    main = [c for n, c in plan if not n.endswith('diagnostic')]
    assert len(main) == 12 and sum(c.hands for c in main) == 120000
    assert {c.agent_b for c in main} == set(m4.OPPONENTS) and all(c.agent_a == 'cfr' for c in main)
    used_before = {1234, 5678, 31001, 31002, 31003, 41001, 41002, 41003, m4.TRAIN_SEED}
    assert not used_before & {s for pair in m4.EVAL_SEEDS for s in pair}
    assert all(c.cfr_policy == m4.SNAPSHOT_POLICY for n, c in plan if n.endswith('diagnostic'))


def test_mission4_analysis_audits_every_cfr_decision(tmp_path, monkeypatch):
    abstraction = Abstraction({'preflop_table_samples': 200, 'postflop_samples': 8})
    paths = []
    for iterations in (10, 30):
        trainer = CFRTrainer(HoldemAbstractGame(abstraction), 'external', seed=1).train(iterations)
        paths.append(str(tmp_path / f'p{iterations}.json.gz'))
        export_policy(trainer, abstraction, tmp_path / f'p{iterations}.json.gz', {})
    monkeypatch.setattr(m4, 'MAIN_HANDS', 6)
    root = tmp_path / 'suite'
    for name, cfg in m4.jobs(paths[1], paths[0]):
        asyncio.run(experiment(cfg, root / name))
    result = m4.analyze(root, tmp_path / 'analysis.json', paths[1], paths[0])
    assert [e['opponent'] for e in result['primary']] == list(m4.OPPONENTS)
    for entry in result['primary']:
        assert entry['hands'] == 18 and entry['verdict'] in ('beats', 'loses', 'inconclusive')
        profits = [entry['rake'][r]['a']['profit_chips'] for r in ('0', '2', '5', '7')]
        assert profits == sorted(profits, reverse=True)
    assert all(r['audit']['decisions'] > 0 for r in result['runs'])
    assert len(result['training_diagnostic']) == 2
    # A tampered decision must fail the replay audit even with a recomputed checksum.
    import hashlib
    folder = root / f'cfr-v-tag-{m4.EVAL_SEEDS[0][0]}'
    lines = (folder / 'decisions.jsonl').read_text().splitlines()
    index = next(i for i, l in enumerate(lines) if json.loads(l)['actor'] == 'a')
    entry = json.loads(lines[index])
    legal = [a['id'] for a in entry['observation']['legal_actions'] if a['id'] != entry['action']]
    entry['action'] = legal[0]
    lines[index] = json.dumps(entry, separators=(',', ':'))
    (folder / 'decisions.jsonl').write_text('\n'.join(lines) + '\n')
    manifest = json.loads((folder / 'experiment.json').read_text())
    manifest['artifacts_sha256']['decisions.jsonl'] = hashlib.sha256((folder / 'decisions.jsonl').read_bytes()).hexdigest()
    (folder / 'experiment.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='not reproduced'):
        asyncio.run(m4.audit_cfr(folder))
