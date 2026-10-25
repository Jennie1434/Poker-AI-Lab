"""Offline audit, preregistered multi-seed suite, and fixed-policy rake analysis."""
import argparse
import asyncio
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
from itertools import groupby
import json
from pathlib import Path
import statistics
import time

from .agents import EquityHeuristicAgent
from .benchmark import Config, derive_seed, experiment, make_agent, performance, settle_rake
from .engine import Hand

# Fixed before observing mission-3 outcomes. Same seeds across matchups permit
# paired comparisons; three master pairs are independent replication units.
SEEDS = ((31001, 41001), (31002, 41002), (31003, 41003))
MATCHUPS = (("equity", "tag"), ("equity", "heuristic"), ("tag", "heuristic"))


def write_json(path, data):
    with Path(path).open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def read_rows(folder):
    with (folder / "hands.csv").open() as f:
        return [{k: v if k == "button" else int(v) for k, v in r.items()} for r in csv.DictReader(f)]


async def audit(folder: Path, output: Path):
    """Replay all hands/observations; reproduce policies on the largest 20 wins/losses."""
    manifest = json.loads((folder / "experiment.json").read_text())
    if manifest["status"] != "complete":
        raise ValueError("Incomplete source experiment")
    cfg = Config(**manifest["config"])
    for name, expected in manifest["artifacts_sha256"].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != expected:
            raise ValueError("Source checksum mismatch")
    rows = read_rows(folder)
    if len(rows) != cfg.hands or [r["hand"] for r in rows] != list(range(1, cfg.hands+1)):
        raise ValueError("Missing or unordered source hands")
    target = "a" if cfg.agent_a == "equity" else "b"
    ordered = lambda sign: sorted((r for r in rows if sign*r[f"{target}_gross_chips"] > 0),
                                 key=lambda r: (-r["contested_pot_chips"], -abs(r[f"{target}_gross_chips"]), r["hand"]))[:20]
    selected = {r["hand"] for r in ordered(1) + ordered(-1)}
    details = []
    counts = Counter()
    action_stats = Counter()
    stage_stats = Counter()
    all_in_net = 0
    with (folder / "decisions.jsonl").open() as f:
        groups = groupby((json.loads(line) for line in f), key=lambda e: e["hand"])
        for row in rows:
            number, entries = next(groups)
            entries = list(entries)
            if number != row["hand"] or len(entries) != row["decisions"]:
                raise ValueError("Trace hand/order mismatch")
            index = number - 1
            if row["button"] != ("a" if index % 2 == 0 else "b"):
                raise ValueError("Position imbalance")
            h = Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}], index % 2,
                     (50, 100, 0), derive_seed(cfg.deck_seed, "deck", index), number, chip_unit=50)
            agents = {seat: make_agent(policy, derive_seed(cfg.policy_seed, f"policy:{seat}", index), cfg.equity_samples, cfg.tag_samples)
                      for seat, policy in (("a", cfg.agent_a), ("b", cfg.agent_b))} if number in selected else None
            all_in = False
            decisions = []
            for sequence, entry in enumerate(entries, 1):
                obs = entry["observation"]
                if entry["actor"] != h.actor or entry["decision"] != sequence or obs != h.observation():
                    raise ValueError(f"Observation or actor mismatch in hand {number}")
                for seat in obs["seats"]:
                    if seat["id"] != obs["actor"] and seat["cards"] != seat["public_cards"]:
                        raise ValueError("Hidden-card leak")
                choices = {a.id: a for a in h.legal()}
                if entry["action"] not in choices:
                    raise ValueError("Illegal trace action")
                chosen = choices[entry["action"]]
                all_in |= chosen.all_in
                if agents:
                    chosen_again = await agents[h.actor].choose_action(obs)
                    if chosen_again != entry["action"]:
                        raise ValueError(f"Policy reproduction mismatch in hand {number}")
                if h.actor == target:
                    action_stats[f"{obs['street']}:{chosen.kind}"] += 1
                    stage_stats[obs['street']] += 1
                    if obs['street'] == 'preflop' and obs['to_call']:
                        action_stats['preflop_facing_bet'] += 1
                        action_stats['preflop_folds_facing_bet'] += chosen.kind == 'fold'
                    if obs['street'] == 'preflop' and 'BB' == next(s['position'] for s in obs['seats'] if s['id'] == obs['actor']):
                        action_stats['bb_facing_bet'] += bool(obs['to_call'])
                        action_stats['bb_fold_facing_bet'] += bool(obs['to_call']) and chosen.kind == 'fold'
                if agents:
                    decisions.append({"actor": h.actor, "street": obs["street"], "action": chosen.id,
                                      "pay_chips": chosen.pay, "pot_before": obs["pot"], "all_in": chosen.all_in})
                h.apply(chosen.id)
                counts['decisions_verified'] += 1
            if h.state.status:
                raise ValueError("Unfinished hand")
            # Independent stack-based profit check, not only reusing rake code.
            final = h.snapshot()["seats"]
            for seat in final:
                if seat["stack"] - 20000 != row[f"{seat['id']}_gross_chips"]:
                    raise ValueError("Profit mismatch")
            settled = settle_rake(h, cfg)
            if settled['pot'] != row['contested_pot_chips'] or settled['rake'] != row['rake_chips'] or int(settled['saw_flop']) != row['saw_flop']:
                raise ValueError("Pot/rake mismatch")
            for seat in ('a', 'b'):
                if settled['net'][seat] != row[f'{seat}_net_chips']:
                    raise ValueError("Net profit mismatch")
            if all_in:
                counts['all_in_hands'] += 1
                all_in_net += row[f'{target}_net_chips']
            if agents:
                details.append({**row, "all_in": all_in, "decisions": decisions,
                                "category": "win" if row[f'{target}_gross_chips'] > 0 else "loss"})
            counts['hands_verified'] += 1
        if next(groups, None) is not None:
            raise ValueError("Extra trace hands")
    result = {"source": str(folder), "target_seat": target, "verified": dict(counts),
              "top_wins": [r['hand'] for r in ordered(1)], "top_losses": [r['hand'] for r in ordered(-1)],
              "top_details": details, "target_action_counts": dict(action_stats),
              "target_street_decisions": dict(stage_stats), "target_all_in_net_bb": all_in_net/100,
              "target_other_net_bb": (sum(r[f'{target}_net_chips'] for r in rows)-all_in_net)/100,
              "hidden_card_mismatches": 0, "profit_mismatches": 0,
              "policy_reproduced_hands": len(selected)}
    write_json(output, result)
    return result


def jobs():
    for deck, policy in SEEDS:
        for a, b in MATCHUPS:
            yield f'{a}-v-{b}-{deck}-s64', Config(agent_a=a, agent_b=b, deck_seed=deck, policy_seed=policy, measure_time=True)
    # Secondary diagnostic, predeclared smaller size due to 16x equity cost.
    # Reuse the first 1,000 hands of the first main equity/tag run at 64.
    for samples in (256, 1024):
        yield f'equity-v-tag-{SEEDS[0][0]}-s{samples}-diagnostic', Config(hands=1000, agent_a='equity', agent_b='tag',
                deck_seed=SEEDS[0][0], policy_seed=SEEDS[0][1], equity_samples=samples, tag_samples=64, measure_time=True)


def run_job(job):
    name, cfg, root = job
    started, cpu = time.perf_counter(), time.process_time()
    result = asyncio.run(experiment(cfg, root/name))
    timing = {'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu,
              'config': asdict(cfg)}
    write_json(root/name/'runtime.json', timing)
    return name, result['summary'], timing


def run_suite(root, workers):
    plan = list(jobs())
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(root/'plan.json', {'workers': workers, 'jobs': {name: asdict(cfg) for name,cfg in plan},
                               'primary_hands': 90000, 'diagnostic_hands': 2000,
                               'rake_rates': [0,2,5,7], 'rake_cap_bb': 3})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, (name,cfg,root)) for name,cfg in plan]
        for future in as_completed(futures):
            name, summary, timing = future.result()
            print(json.dumps({'finished': name, 'hands': summary['completed_hands'], 'cpu_seconds': timing['cpu_seconds']}), flush=True)


def rerake(row, rate, cap=300):
    """Independent CSV ledger, reproducing the documented HU allocation exactly."""
    pot = row['contested_pot_chips']
    rake = int(min(Decimal(pot)*Decimal(str(rate))/100, Decimal(cap))) if row['saw_flop'] else 0
    payouts = {seat: row[f'{seat}_gross_chips'] + pot//2 for seat in ('a','b')}
    charges = {s: rake*payouts[s]//pot if pot else 0 for s in payouts}
    order = sorted(payouts, key=lambda s: -(rake*payouts[s]%pot) if pot else 0)
    for seat in order[:rake-sum(charges.values())]:
        charges[seat] += 1
    return {s: row[f'{s}_gross_chips']-charges[s] for s in payouts}


def summarize_values(values):
    return performance(values)


def analyze(root, output):
    groups = defaultdict(list)
    per_run = []
    reports = {}
    for name, cfg in jobs():
        folder = root/name
        m = json.loads((folder/'experiment.json').read_text())
        if m['status'] != 'complete' or m['config'] != asdict(cfg):
            raise ValueError('Missing or incompatible experiment')
        rows = read_rows(folder)
        if len(rows) != cfg.hands or [r['button'] for r in rows] != ['a','b']*(cfg.hands//2):
            raise ValueError('Incomplete or unbalanced experiment')
        for artifact, checksum in m['artifacts_sha256'].items():
            if hashlib.sha256((folder/artifact).read_bytes()).hexdigest() != checksum:
                raise ValueError('Artifact checksum mismatch')
        for row in rows:
            if rerake(row, 5) != {s:row[f'{s}_net_chips'] for s in ('a','b')}:
                raise ValueError('Independent rake mismatch')
        reports[name] = (m, rows)
        per_run.append({'name': name, 'config': asdict(cfg), 'summary': m['summary'],
                        'timing': m['decision_bridge_timing'], 'runtime': json.loads((folder/'runtime.json').read_text())})
        if cfg.hands == 10000:
            groups[(cfg.agent_a,cfg.agent_b)].append(rows)
    combined = []
    for (a,b), sets in groups.items():
        rows = [r for block in sets for r in block]
        entry = {'agent_a':a, 'agent_b':b, 'hands':len(rows), 'seeds':len(sets), 'rake':{}}
        for rate in (0,2,5,7):
            ledger = [rerake(r,rate) for r in rows]
            entry['rake'][str(rate)] = {seat:performance([r[seat] for r in ledger]) for seat in ('a','b')}
        entry['seed_means_net_bb100'] = [performance([r['a_net_chips'] for r in rows])['bb_per_100'] for rows in sets]
        entry['sd_seed_means_bb100'] = statistics.stdev(entry['seed_means_net_bb100'])
        combined.append(entry)
    base_name = f'equity-v-tag-{SEEDS[0][0]}-s64'
    base = reports[base_name][1][:1000]
    sensitivity = []
    for samples in (64,256,1024):
        name = base_name if samples == 64 else f'equity-v-tag-{SEEDS[0][0]}-s{samples}-diagnostic'
        m, rows = reports[name]
        rows = rows[:1000]
        sensitivity.append({'samples':samples, 'hands':1000,
                            'equity_net': performance([r['a_net_chips'] for r in rows]),
                            'paired_delta_vs_64': performance([r['a_net_chips']-b['a_net_chips'] for r,b in zip(rows,base)]),
                            'timing_scope_hands':m['summary']['completed_hands'],
                            'equity_decision_timing':m['decision_bridge_timing']['a']})
    result = {'primary': combined, 'runs':per_run, 'equity_samples_diagnostic':sensitivity,
              'rake_cap_bb':3, 'no_flop_no_drop':True,
              'ci_method':'normal 95% on independent two-hand block means; per-seed results also reported'}
    write_json(output, result)
    with output.with_suffix('.csv').open('x', newline='') as f:
        fields=['matchup','hands','rake_percent','seat','bb100_net','ci_low','ci_high','sd_hand_bb']
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for entry in combined:
            for rate, seats in entry['rake'].items():
                for seat, metrics in seats.items():
                    writer.writerow(dict(matchup=entry['agent_a']+'-v-'+entry['agent_b'],hands=entry['hands'],rake_percent=rate,
                        seat=seat,bb100_net=metrics['bb_per_100'],ci_low=metrics['ci95_bb_per_100'][0],
                        ci_high=metrics['ci95_bb_per_100'][1],sd_hand_bb=metrics['stddev_hand_bb']))
    return result


async def cost_diagnostic(source, output):
    # Fixed public/actor-only states; deterministic first 50 per street.
    cases = defaultdict(list)
    with (source/'decisions.jsonl').open() as f:
        for line in f:
            e=json.loads(line)
            obs=e['observation']; street=obs['street']
            if e['actor']=='b' and len(cases[street])<50:
                cases[street].append(obs)
            if sum(map(len,cases.values()))==200:
                break
    results=[]
    for street, observations in cases.items():
        for index, obs in enumerate(observations):
            for samples in (64,256,1024):
                agent=EquityHeuristicAgent(derive_seed(991,street,index),samples)
                start=time.process_time()
                action=await agent.choose_action(obs)
                results.append({'street':street,'case':index,'samples':samples,'action':action,
                                'cpu_seconds':time.process_time()-start})
    write_json(output, {'sampling':'first 50 equity decisions per street from mission2, descriptive only', 'results':results})


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command', required=True)
    for command in ('audit','cost'):
        s=sub.add_parser(command);s.add_argument('source',type=Path);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('run');s.add_argument('--output',type=Path,required=True);s.add_argument('--workers',type=int,default=3)
    s=sub.add_parser('analyze');s.add_argument('source',type=Path);s.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='audit':asyncio.run(audit(a.source,a.output))
    elif a.command=='cost':asyncio.run(cost_diagnostic(a.source,a.output))
    elif a.command=='run':run_suite(a.output,a.workers)
    else:analyze(a.source,a.output)


if __name__=='__main__':
    main()
