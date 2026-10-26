"""Supplementary offline review of audited hands and decision frequencies.

Run with the repository virtualenv. Outputs contain no private hole cards.
"""
import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict
import hashlib
import json
import random
import statistics
import math
from pathlib import Path

from treys import Card, Evaluator
from pokerbench.benchmark import Config, derive_seed
from pokerbench.engine import Hand
from pokerbench.agents import EquityHeuristicAgent


def showdown_check(source, audit_file, output):
    cfg=Config(**json.loads((source/'experiment.json').read_text())['config'])
    audited=json.loads(audit_file.read_text())
    records=[]
    evaluator=Evaluator()
    for row in audited['top_details']:
        index=row['hand']-1
        h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],index%2,(50,100,0),
               derive_seed(cfg.deck_seed,'deck',index),index+1,chip_unit=50)
        for decision in row['decisions']:
            h.apply(decision['action'])
        checked=False
        if not h.folded:
            board=[Card.new(c) for c in h.snapshot()['board']]
            scores={pid:evaluator.evaluate(board,[Card.new(c) for c in cards]) for pid,cards in h.original_holes.items()}
            expected=1 if scores['a']<scores['b'] else -1 if scores['a']>scores['b'] else 0
            profit=next(s['payoff'] for s in h.snapshot()['seats'] if s['id']=='a')
            actual=1 if profit>0 else -1 if profit<0 else 0
            if actual!=expected:
                raise ValueError('Independent showdown ranking mismatch')
            checked=True
        records.append({'hand':row['hand'],'category':row['category'],
                        'pot_bb':row['contested_pot_chips']/100,
                        'target_net_bb':row[f"{audited['target_seat']}_net_chips"]/100,
                        'all_in':row['all_in'], 'last_street':row['decisions'][-1]['street'],
                        'last_actor':row['decisions'][-1]['actor'],'last_action':row['decisions'][-1]['action'],
                        'showdown_independently_checked':checked})
    data={'source':str(source),'hands':records,'showdown_checks':sum(r['showdown_independently_checked'] for r in records),
          'review_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with output.open('x') as f:json.dump(data,f,indent=2)


def frequencies(root, output):
    report=[]
    for manifest in sorted(root.glob('*/experiment.json')):
        m=json.loads(manifest.read_text())
        if m['status']!='complete' or m['config']['hands']!=10000:
            continue
        cfg=m['config']; folder=manifest.parent
        counters={s:Counter() for s in ('a','b')}
        sets={s:defaultdict(set) for s in ('a','b')}
        with (folder/'decisions.jsonl').open() as f:
            for line in f:
                e=json.loads(line);seat=e['actor'];obs=e['observation']; street=obs['street']
                action=next(a for a in obs['legal_actions'] if a['id']==e['action'])
                actor=next(s for s in obs['seats'] if s['id']==obs['actor'])
                counters[seat][street+':'+action['kind']]+=1
                counters[seat]['all_in_actions']+=int(action['all_in'])
                if street=='preflop':
                    if action['kind'] in ('raise','call'): sets[seat]['vpip'].add(e['hand'])
                    if action['kind']=='raise': sets[seat]['pfr'].add(e['hand'])
                    if actor['position']=='BB' and obs['to_call']:
                        sets[seat]['bb_facing_bet'].add(e['hand'])
                        if action['kind']=='fold':sets[seat]['bb_fold_facing_bet'].add(e['hand'])
                elif obs['to_call']:
                    counters[seat]['postflop_facing_bet']+=1
                    counters[seat]['postflop_fold_facing_bet']+=action['kind']=='fold'
        with (folder/'hands.csv').open() as f: rows=list(csv.DictReader(f))
        agents={}
        for seat in ('a','b'):
            positions={}
            for position in ('BTN','BB'):
                selected=[r for r in rows if (r['button']==seat)==(position=='BTN')]
                positions[position]={'hands':len(selected),'net_bb100':sum(int(r[f'{seat}_net_chips']) for r in selected)/len(selected)}
            agents[seat]={'policy':cfg['agent_'+seat],'counts':dict(counters[seat]),
                          'hand_counts':{k:len(v) for k,v in sets[seat].items()},'positions':positions}
        report.append({'run':folder.name,'agents':agents})
    with output.open('x') as f:json.dump(report,f,indent=2,sort_keys=True)


def postmortem(source, audit_file, output):
    """After-the-fact equity diagnostic, NEVER an observation or policy input.

    Compare uniform-opponent equity to equity against the now-known opponent
    on the public board at the last Equity decision of each selected hand.
    No future board cards are used; selected-loss bias is explicit.
    """
    cfg=Config(**json.loads((source/'experiment.json').read_text())['config'])
    audited=json.loads(audit_file.read_text())
    target=audited['target_seat']; results=[]; evaluator=Evaluator()
    for row in audited['top_details']:
        index=row['hand']-1
        h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],index%2,(50,100,0),
               derive_seed(cfg.deck_seed,'deck',index),index+1,chip_unit=50)
        own_decisions=[i for i,d in enumerate(row['decisions']) if d['actor']==target]
        if not own_decisions:continue
        final=own_decisions[-1]
        for i,decision in enumerate(row['decisions']):
            if i==final:
                obs=h.observation()
                uniform=EquityHeuristicAgent(derive_seed(997,'uniform',index),1024).estimate_equity(obs)
                board=[Card.new(c) for c in obs['board']]
                hero=[Card.new(c) for c in h.original_holes[target]]
                villain=[Card.new(c) for c in h.original_holes['b' if target=='a' else 'a']]
                known=set(board+hero+villain)
                deck=[Card.new(r+s) for r in '23456789TJQKA' for s in 'cdhs' if Card.new(r+s) not in known]
                rng=random.Random(derive_seed(998,'postmortem',index)); wins=0
                for _ in range(1024):
                    full_board=board+rng.sample(deck,5-len(board))
                    hs=evaluator.evaluate(full_board,hero);vs=evaluator.evaluate(full_board,villain)
                    wins+=1 if hs<vs else .5 if hs==vs else 0
                results.append({'hand':row['hand'],'category':row['category'], 'street':obs['street'],
                    'last_equity_action':decision['action'],'pay_chips':decision['pay_chips'],
                    'uniform_equity':uniform,'actual_opponent_equity_posthoc':wins/1024,
                    'pot_odds':obs['to_call']/(obs['pot']+obs['to_call']) if obs['to_call'] else 0})
            h.apply(decision['action'])
    with output.open('x') as f:json.dump({'scope':'selected large wins/losses, posthoc known opponent, no future board; not an agent input',
        'samples':1024,'results':results},f,indent=2)


def river_range_check(source, output):
    """Outcome-blind sample: first facing-bet river decision per Equity hand."""
    cfg=Config(**json.loads((source/'experiment.json').read_text())['config'])
    target='a' if cfg.agent_a=='equity' else 'b'
    candidates={}
    with (source/'decisions.jsonl').open() as f:
        for line in f:
            e=json.loads(line);obs=e['observation']
            if e['actor']==target and obs['street']=='river' and obs['to_call'] and e['hand'] not in candidates:
                candidates[e['hand']]=e
    chosen=sorted(candidates, key=lambda n:derive_seed(20261025,'range-audit',n))[:200]
    evaluator=Evaluator();results=[]
    for number in chosen:
        obs=candidates[number]['observation'];index=number-1
        h=Hand([{'id':'a','stack':20000},{'id':'b','stack':20000}],index%2,(50,100,0),
               derive_seed(cfg.deck_seed,'deck',index),number,chip_unit=50)
        for action in obs['history']:h.apply(action['id'])
        if h.observation()!=obs:raise ValueError('Range diagnostic reconstruction mismatch')
        board=[Card.new(c) for c in obs['board']]
        own=evaluator.evaluate(board,[Card.new(c) for c in h.original_holes[target]])
        other=evaluator.evaluate(board,[Card.new(c) for c in h.original_holes['b' if target=='a' else 'a']])
        actual=1 if own<other else .5 if own==other else 0
        uniform=EquityHeuristicAgent(derive_seed(8801,'range-equity',number),1024).estimate_equity(obs)
        results.append({'hand':number,'uniform_equity':uniform,'actual_showdown_share':actual,
                        'action':candidates[number]['action']})
    differences=[r['uniform_equity']-r['actual_showdown_share'] for r in results]
    mean=statistics.mean(differences);se=statistics.stdev(differences)/math.sqrt(len(differences))
    report={'scope':'First facing-bet river decision per hand; 200 smallest deterministic hashes, no outcome selection. Actual cards only used by offline auditor.',
            'eligible_hands':len(candidates),'sample_size':len(results),
            'mean_uniform_equity':statistics.mean(r['uniform_equity'] for r in results),
            'mean_actual_showdown_share':statistics.mean(r['actual_showdown_share'] for r in results),
            'mean_gap':mean,'normal_ci95_gap':[mean-1.96*se,mean+1.96*se],'results':results}
    with output.open('x') as f:json.dump(report,f,indent=2)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('showdowns');s.add_argument('source',type=Path);s.add_argument('audit',type=Path);s.add_argument('output',type=Path)
    s=sub.add_parser('postmortem');s.add_argument('source',type=Path);s.add_argument('audit',type=Path);s.add_argument('output',type=Path)
    s=sub.add_parser('ranges');s.add_argument('source',type=Path);s.add_argument('output',type=Path)
    s=sub.add_parser('frequencies');s.add_argument('source',type=Path);s.add_argument('output',type=Path)
    a=p.parse_args()
    if a.command=='showdowns':showdown_check(a.source,a.audit,a.output)
    elif a.command=='postmortem':postmortem(a.source,a.audit,a.output)
    elif a.command=='ranges':river_range_check(a.source,a.output)
    else:frequencies(a.source,a.output)


if __name__=='__main__':main()
