import json

import pytest

from pokerbench.cfr import (CFRTrainer, best_response_value, exploitability, expected_value,
                            load_checkpoint, regret_matching)
from pokerbench.selfplay import train_toy
from pokerbench.toy_games import KUHN_VALUE, KuhnPoker, LeducPoker

LEDUC_VALUE = -0.0856  # published player-0 equilibrium value, 4 decimals


def kuhn_nash(alpha=0.0):
    """Closed-form Kuhn equilibrium family (player 0 bluff parameter alpha)."""
    s = lambda bet: {'p': 1 - bet, 'b': bet}
    return {'J:': s(alpha), 'Q:': s(0), 'K:': s(3 * alpha),
            'J:pb': s(0), 'Q:pb': s(alpha + 1 / 3), 'K:pb': s(1),
            'J:b': s(0), 'Q:b': s(1 / 3), 'K:b': s(1),
            'J:p': s(1 / 3), 'Q:p': s(0), 'K:p': s(1)}


def test_regret_matching_normalizes_positive_regrets_only():
    assert regret_matching([1, 3, -5]) == [0.25, 0.75, 0]
    assert regret_matching([-1, 0]) == [0.5, 0.5]


@pytest.mark.parametrize('alpha', [0, 1 / 6, 1 / 3])
def test_best_response_certifies_known_kuhn_equilibria(alpha):
    metrics = exploitability(KuhnPoker(), kuhn_nash(alpha))
    assert metrics['exploitability'] == pytest.approx(0, abs=1e-12)
    assert metrics['value_p0'] == pytest.approx(KUHN_VALUE, abs=1e-12)


def test_best_response_punishes_non_equilibrium_and_is_bounded_by_payoffs():
    game = KuhnPoker()
    always_bet = {k: {'p': 0.0, 'b': 1.0} for k in kuhn_nash()}
    metrics = exploitability(game, always_bet)
    assert metrics['exploitability'] > 0.1
    # A best response is at least as good as the strategy's own play, for both players.
    assert best_response_value(game, always_bet, 0) >= expected_value(game, always_bet) - 1e-12
    assert best_response_value(game, always_bet, 1) >= -expected_value(game, always_bet) - 1e-12
    assert exploitability(game, {})['exploitability'] > 0  # uniform default


def test_kuhn_cfr_plus_converges_to_equilibrium_family():
    trainer = CFRTrainer(KuhnPoker(), 'plus').train(2000)
    strategy = trainer.average_strategy()
    metrics = exploitability(KuhnPoker(), strategy)
    assert metrics['exploitability'] < 1e-3
    assert metrics['value_p0'] == pytest.approx(KUHN_VALUE, abs=2e-3)
    bet = lambda key: strategy[key]['b']
    alpha = bet('J:')
    assert 0 <= alpha <= 1 / 3 + 0.02
    assert bet('K:') == pytest.approx(3 * alpha, abs=0.03)
    assert bet('Q:') < 0.02
    assert bet('Q:pb') == pytest.approx(alpha + 1 / 3, abs=0.03)
    assert bet('K:b') > 0.98 and bet('K:p') > 0.98 and bet('J:b') < 0.02
    assert bet('J:p') == pytest.approx(1 / 3, abs=0.03) and bet('Q:b') == pytest.approx(1 / 3, abs=0.03)


@pytest.mark.parametrize('variant', ['vanilla', 'plus', 'external'])
def test_kuhn_exploitability_decreases_for_every_trainer(variant):
    game, trainer = KuhnPoker(), CFRTrainer(KuhnPoker(), variant, seed=3)
    early = exploitability(game, trainer.train(50).average_strategy())['exploitability']
    late = exploitability(game, trainer.train(4950).average_strategy())['exploitability']
    assert late < early and late < 0.05


def test_leduc_rules_payoffs_and_tree():
    g = LeducPoker()
    # J,Q private; player 1 (Q) pairs a Q board.
    h = ((0, 2), 3, ('rc', 'rc'))
    assert g.is_terminal(h) and g.contributions(h) == [7, 7] and g.utility(h) == -7
    assert g.utility(((0, 2), 1, ('rc', 'rc'))) == 7       # J pairs J board
    assert g.utility(((0, 1), 4, ('cc', 'cc'))) == 0       # same rank splits
    assert g.utility(((4, 0), None, ('rrf',))) == -3       # p1 re-raised, p0 folds 1+2
    assert g.utility(((4, 0), 2, ('cc', 'rf'))) == 1       # p1 folds the ante
    assert g.actions(((0, 2), None, ('',))) == ('c', 'r')
    assert g.actions(((0, 2), None, ('rr',))) == ('f', 'c')
    assert g.is_chance(((0, 2), None, ('cc',))) and not g.is_terminal(((0, 2), None, ('cc',)))
    keys = set()

    def walk(h):
        if g.is_terminal(h):
            return
        if g.is_chance(h):
            for a, _ in g.chance_outcomes(h):
                walk(g.child(h, a))
            return
        deal, public, rounds = h
        # The key must not change when only the opponent's private card changes.
        opponent = 1 - g.player(h)
        for other in range(6):
            if other not in (deal[g.player(h)], public):
                swapped = list(deal); swapped[opponent] = other
                assert g.infoset((tuple(swapped), public, rounds)) == g.infoset(h)
        keys.add(g.infoset(h))
        for a in g.actions(h):
            walk(g.child(h, a))
    walk(g.root())
    assert len(keys) == 288  # rank-isomorphic information sets


def test_leduc_cfr_plus_converges_near_published_value():
    game = LeducPoker()
    trainer = CFRTrainer(game, 'plus')
    early = exploitability(game, trainer.train(10).average_strategy())['exploitability']
    metrics = exploitability(game, trainer.train(70).average_strategy())
    assert metrics['exploitability'] < 0.03 < early
    assert metrics['value_p0'] == pytest.approx(LEDUC_VALUE, abs=0.01)


def test_leduc_external_sampling_converges_and_is_seed_reproducible():
    game = LeducPoker()
    a = CFRTrainer(game, 'external', seed=11).train(2000)
    early = exploitability(game, a.average_strategy())['exploitability']
    b = CFRTrainer(game, 'external', seed=11).train(2000)
    assert a.state() == b.state()
    assert CFRTrainer(game, 'external', seed=12).train(2000).state()['sha256'] != a.state()['sha256']
    late = exploitability(game, a.train(18000).average_strategy())['exploitability']
    assert late < 0.25 and late < early / 2


@pytest.mark.parametrize('variant', ['plus', 'external'])
def test_checkpoint_resume_equals_continuous_training(tmp_path, variant):
    game = LeducPoker() if variant == 'external' else KuhnPoker()
    continuous = CFRTrainer(game, variant, seed=5).train(40)
    first = CFRTrainer(game, variant, seed=5).train(15)
    first.save(tmp_path / 'c.json', {'note': 'x'})
    resumed = CFRTrainer.load(game, tmp_path / 'c.json').train(25)
    assert resumed.state() == continuous.state()
    assert load_checkpoint(tmp_path / 'c.json')['metadata'] == {'note': 'x'}


def test_checkpoint_rejects_tampering_wrong_game_and_overwrite(tmp_path):
    path = tmp_path / 'k.json'
    CFRTrainer(KuhnPoker(), 'plus').train(5).save(path)
    with pytest.raises(FileExistsError):
        CFRTrainer(KuhnPoker(), 'plus').save(path)
    with pytest.raises(ValueError, match='leduc'):
        CFRTrainer.load(LeducPoker(), path)
    data = json.loads(path.read_text())
    data['strategy_sum']['K:'][1] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='checksum'):
        CFRTrainer.load(KuhnPoker(), path)


def test_toy_training_cli_logs_convergence_and_resumes(tmp_path):
    summary = train_toy('kuhn', 'plus', 200, tmp_path / 'run', every=50)
    rows = (tmp_path / 'run' / 'convergence.csv').read_text().splitlines()
    assert len(rows) == 5 and summary['final']['exploitability'] < 0.01
    with pytest.raises(FileExistsError):
        train_toy('kuhn', 'plus', 10, tmp_path / 'run')
    resumed = train_toy('kuhn', 'plus', 100, tmp_path / 'more', resume=tmp_path / 'run' / 'checkpoint.json')
    assert resumed['iterations'] == 300
