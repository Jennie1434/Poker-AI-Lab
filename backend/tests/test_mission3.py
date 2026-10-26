from copy import deepcopy
import json
from dataclasses import replace

import pytest

from pokerbench.agents import TightAggressiveAgent
from pokerbench.benchmark import Config, experiment, performance
from pokerbench.engine import Hand
from pokerbench.mission3 import audit, jobs, rerake, read_rows


def observation(cards):
    h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],0,(50,100,0),42)
    obs=h.observation()
    next(s for s in obs['seats'] if s['id']==obs['actor'])['cards']=cards
    return obs


@pytest.mark.parametrize('cards,tier', [(['As','Ah'],4),(['As','Kh'],4),(['9s','9h'],3),(['Ac','Jc'],3),
                                       (['2s','2h'],2),(['Ac','5c'],2),(['6s','5s'],1),(['7s','2h'],0)])
def test_tag_explicit_preflop_selection(cards,tier):
    assert TightAggressiveAgent.preflop_tier(cards)==tier


@pytest.mark.asyncio
async def test_tag_opens_selected_hands_folds_trash_and_defends_big_blind():
    tag=TightAggressiveAgent(1)
    assert (await tag.choose_action(observation(['As','Ah']))).startswith('raise_to_')
    assert await tag.choose_action(observation(['7s','2h']))=='fold'
    h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],0,(50,100,0),1)
    h.apply('raise_to_300')
    obs=h.observation()
    next(s for s in obs['seats'] if s['id']==obs['actor'])['cards']=['Js','Th']
    assert await tag.choose_action(obs)=='call'


@pytest.mark.asyncio
async def test_tag_preflop_risk_rejects_speculative_all_in():
    h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],0,(50,100,0),42)
    h.apply('raise_to_20000')
    obs=h.observation()
    hero=next(s for s in obs['seats'] if s['id']==obs['actor'])
    hero['cards']=['9s','Ts']
    assert await TightAggressiveAgent(1).choose_action(obs)=='fold'
    hero['cards']=['As','Ah']
    assert await TightAggressiveAgent(1).choose_action(obs)=='call'


@pytest.mark.asyncio
async def test_tag_postflop_price_and_risk(monkeypatch):
    tag=TightAggressiveAgent(1)
    h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],0,(50,100,0),42)
    h.apply('call');h.apply('check');h.apply('raise_to_19900')
    monkeypatch.setattr(tag,'estimate_equity',lambda _:0.70)
    assert await tag.choose_action(h.observation())=='fold'
    monkeypatch.setattr(tag,'estimate_equity',lambda _:0.95)
    assert await tag.choose_action(h.observation())=='call'


def test_tag_draw_detection():
    assert TightAggressiveAgent.has_draw(['Ah','Kh'],['2h','9h','3c'])
    assert TightAggressiveAgent.has_draw(['8c','9d'],['Th','Js','2c'])
    assert not TightAggressiveAgent.has_draw(['2c','7d'],['Kh','9s','3c'])
    assert not TightAggressiveAgent.has_draw(['Ah','Kh'],['2h','9h','3c','4s','5s'])


@pytest.mark.asyncio
async def test_tag_ignores_hidden_cards_and_is_reproducible():
    obs=observation(['As','Kh'])
    changed=deepcopy(obs)
    next(s for s in changed['seats'] if s['id']!=changed['actor'])['cards']=['Ac','Ad']
    assert await TightAggressiveAgent(9).choose_action(obs)==await TightAggressiveAgent(9).choose_action(changed)


@pytest.mark.asyncio
async def test_audit_replays_all_hands_and_detects_corrupt_observation(tmp_path):
    cfg=Config(hands=10,agent_a='equity',agent_b='tag',equity_samples=8,tag_samples=8)
    folder=tmp_path/'source'
    await experiment(cfg,folder)
    result=await audit(folder,tmp_path/'audit.json')
    assert result['verified']['hands_verified']==10
    assert result['hidden_card_mismatches']==0
    assert len(result['top_details'])>0
    # Modify trace and update checksum so the replay, rather than hashing, must catch it.
    import hashlib
    trace=folder/'decisions.jsonl'
    entries=[json.loads(l) for l in trace.read_text().splitlines()]
    obs=entries[0]['observation']
    next(s for s in obs['seats'] if s['id']!=obs['actor'])['cards']=['Ac','Ad']
    trace.write_text('\n'.join(json.dumps(e) for e in entries)+'\n')
    m=json.loads((folder/'experiment.json').read_text())
    m['artifacts_sha256']['decisions.jsonl']=hashlib.sha256(trace.read_bytes()).hexdigest()
    (folder/'experiment.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='Observation'):
        await audit(folder,tmp_path/'bad.json')


@pytest.mark.asyncio
async def test_rake_sensitivity_reproduces_existing_ledger_and_is_monotone(tmp_path):
    await experiment(Config(hands=20),tmp_path/'run')
    for row in read_rows(tmp_path/'run'):
        assert rerake(row,5)=={s:row[f'{s}_net_chips'] for s in ('a','b')}
        assert rerake(row,0)=={s:row[f'{s}_gross_chips'] for s in ('a','b')}
        for seat in ('a','b'):
            vals=[rerake(row,rate)[seat] for rate in (0,2,5,7)]
            assert vals==sorted(vals,reverse=True)


def test_preregistered_plan_sizes_seeds_and_fixed_tag_budget():
    plan=list(jobs())
    main=[cfg for _,cfg in plan if cfg.hands==10000]
    assert len(main)==9
    assert len({(c.deck_seed,c.policy_seed) for c in main})==3
    assert sum(c.hands for c in main)==90000
    assert all(c.tag_samples==64 for _,c in plan)
    assert sorted(c.equity_samples for _,c in plan if c.hands==1000)==[256,1024]


def test_dispersion_is_in_bb_per_hand_not_standard_error():
    metrics=performance([0,200,200,400])
    assert metrics['stddev_hand_bb']==pytest.approx((8/3)**0.5)
    assert metrics['stddev_block_mean_bb']==pytest.approx(2**0.5)


async def tiny_suite(tmp_path, monkeypatch):
    import pokerbench.mission3 as m3
    monkeypatch.setattr(m3, 'MAIN_HANDS', 8)
    monkeypatch.setattr(m3, 'DIAGNOSTIC_HANDS', 4)
    root = tmp_path/'suite'
    for name, cfg in m3.jobs():
        await experiment(cfg, root/name)
        (root/name/'runtime.json').write_text(json.dumps({'wall_seconds': 0, 'cpu_seconds': 0}))
    return m3, root


@pytest.mark.asyncio
async def test_analyze_aggregates_seeds_rake_and_sample_diagnostic(tmp_path, monkeypatch):
    m3, root = await tiny_suite(tmp_path, monkeypatch)
    result = m3.analyze(root, root/'analysis.json')
    assert {(e['agent_a'], e['agent_b']) for e in result['primary']} == set(m3.MATCHUPS)
    for entry in result['primary']:
        assert entry['hands'] == 24 and entry['seeds'] == 3 and len(entry['seed_means_net_bb100']) == 3
        rows = [r for deck, _ in m3.SEEDS for r in read_rows(root/f"{entry['agent_a']}-v-{entry['agent_b']}-{deck}-s64")]
        assert entry['rake']['0']['a']['profit_chips'] == sum(r['a_gross_chips'] for r in rows)
        assert entry['rake']['5']['a']['profit_chips'] == sum(r['a_net_chips'] for r in rows)
        for seat in ('a', 'b'):
            profits = [entry['rake'][rate][seat]['profit_chips'] for rate in ('0', '2', '5', '7')]
            assert profits == sorted(profits, reverse=True)
    samples = {d['samples']: d for d in result['equity_samples_diagnostic']}
    assert sorted(samples) == [64, 256, 1024]
    assert samples[64]['paired_delta_vs_64']['profit_chips'] == 0
    assert (root/'analysis.csv').read_text().count('\n') == 1 + 3*4*2


@pytest.mark.asyncio
async def test_analyze_rejects_altered_or_missing_trace(tmp_path, monkeypatch):
    m3, root = await tiny_suite(tmp_path, monkeypatch)
    trace = root/f'equity-v-tag-{m3.SEEDS[0][0]}-s64'/'decisions.jsonl'
    trace.write_bytes(trace.read_bytes() + b' ')
    with pytest.raises(ValueError, match='checksum'):
        m3.analyze(root, root/'analysis.json')
    trace.unlink()
    with pytest.raises(FileNotFoundError):
        m3.analyze(root, root/'analysis2.json')
