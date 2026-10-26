import asyncio

from pokerbench.benchmark import experiment
import pokerbench.mission6 as m6

EARLIER = {1234, 5678, 31001, 31002, 31003, 41001, 41002, 41003, 51001, 51002, 51003, 61001, 61002, 61003,
           71001, 72001, 72002, 81001, 81002, 81003, 91001, 91002, 91003, 83001, 83002, 83003, 93001, 93002, 93003}


def test_mission6_seeds_are_new_and_disjoint():
    baseline = {s for pair in m6.BASELINE_SEEDS for s in pair}
    final = {s for pair in m6.FINAL_SEEDS for s in pair}
    assert not (baseline | final) & EARLIER and not baseline & final
    plan = list(m6.jobs(m6.BASELINE_POLICIES, m6.BASELINE_SEEDS))
    assert len(plan) == 12 and {c.agent_b for _, c in plan} == set(m6.OPPONENTS)


def test_mission6_analysis_reports_positions_frequencies_and_pairs(tmp_path, monkeypatch):
    monkeypatch.setattr(m6, 'MAIN_HANDS', 6)
    policies = {'v1': 'artifacts/mission4/policy-71001-200000.json.gz', 'v2': m6.BASELINE_POLICIES['v2']}
    seeds = m6.BASELINE_SEEDS
    root = tmp_path / 's'
    for name, cfg in m6.jobs(policies, seeds, ('hyper', 'station')):
        asyncio.run(experiment(cfg, root / name))
    result = m6.analyze(root, tmp_path / 'a.json', policies, seeds, ('hyper', 'station'), comparisons=(('v2', 'v1'),))
    assert len(result['results']) == 4 and len(result['paired']) == 2
    for entry in result['results']:
        assert entry['hands'] == 18 and set(entry['position_net_bb100']) == {'BTN', 'BB'}
        # Positions split the pooled result exactly.
        total = entry['rake']['5']['bb_per_100']
        assert abs((entry['position_net_bb100']['BTN'] + entry['position_net_bb100']['BB']) / 2 - total) < 1e-9
    freq = result['runs'][0]['frequencies']
    assert 'preflop' in freq['streets'] and 0 <= freq['vpip'] <= 1
