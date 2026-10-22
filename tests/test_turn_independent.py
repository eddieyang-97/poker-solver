import copy
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import numpy as np

from benchmarks.turn_independent import (
    compare_fixture, independent_train, install_reference_profile, mapping, product_evaluation, product_profile, product_solver,
)
from benchmarks.turn_reference import IndependentCFR, IndependentTurnGame, State


FIXTURES = json.loads((Path(__file__).resolve().parents[1]/'benchmarks/turn-independent-fixtures.json').read_text())


class IndependentTurnTests(unittest.TestCase):
    def test_sixty_random_policies_in_larger_private_information_games(self):
        rng = np.random.default_rng(1379)
        for fixture in FIXTURES[6:]:
            game = IndependentTurnGame(fixture['config'])
            solver = product_solver(fixture['config'])
            for sample in range(15):
                profile = rng.exponential(size=game.uniform.shape)*game.allowed
                profile /= profile.sum(axis=1, keepdims=True)
                install_reference_profile(game, solver, profile)
                expected, actual = game.evaluate(profile), product_evaluation(solver)
                with self.subTest(fixture=fixture['id'], sample=sample):
                    for key in expected:
                        self.assertAlmostEqual(actual[key], expected[key], delta=1e-8, msg=key)

    def test_known_outs_and_concrete_deal_chance(self):
        config = copy.deepcopy(FIXTURES[5]['config'])
        config.update(turn_bet_sizes=[], river_bet_sizes=[])
        config['ip'] = config['ip'][:1]
        game = IndependentTurnGame(config)
        outcomes = [game.sign[0, 0, card] for card in game.legal_rivers[0, 0]]
        self.assertEqual((outcomes.count(1), outcomes.count(-1)), (2, 42))
        diagnostic = game.evaluate(game.uniform)
        self.assertAlmostEqual(diagnostic['oop_ev'], -500/11)
        self.assertAlmostEqual(diagnostic['nash_conv_chips'], 0)
        self.assertEqual(len(game.legal_rivers[0, 0]), 44)
        self.assertEqual(set(game.legal_rivers[0, 0]) & {'Kh', 'Kd', 'As', 'Ad'}, set())
        weighted = IndependentTurnGame(FIXTURES[3]['config'])
        self.assertAlmostEqual(weighted.mass, 1.65)
        root = weighted.records[0]
        probabilities = [weighted.chance_reach[node] for node in root['children']]
        np.testing.assert_allclose(probabilities, np.array([1, 0.5, 0.15])/1.65)
        for node in weighted.records:
            if node['state'] is not None and node['state'].phase == 'river':
                self.assertEqual(len(node['children']), 44)

    def test_independent_chip_ledger_and_allin_transitions(self):
        config = copy.deepcopy(FIXTURES[0]['config'])
        config.update(pot=100, stack=80, river_bet_sizes=[0.5, 1])
        game = IndependentTurnGame(config)
        state = game.next_state(game.next_state(State(), 'B:5000'), 'C')
        self.assertEqual((state.phase, state.committed), ('river', (5000, 5000)))
        state = replace(state, street=1, river='9c', phase='act', player=0, checked=False,
                        history=state.history+('R:9c',))
        self.assertEqual(game.actions(state), ('X', 'B:3000'))
        folded = game.next_state(game.next_state(state, 'B:3000'), 'F')
        self.assertEqual(folded.committed, (8000, 5000))
        self.assertEqual(game.terminal_utility(folded, (0, 0))/100, 100)
        allin_config = copy.deepcopy(FIXTURES[5]['config'])
        allin_config['river_bet_sizes'] = [0.5]
        allin = IndependentTurnGame(allin_config)
        called = allin.next_state(allin.next_state(State(), 'B:10000'), 'C')
        self.assertEqual((called.phase, called.committed), ('river', (10000, 10000)))
        self.assertFalse(any(info['history'][:2] == ('B:10000', 'C') and any(t.startswith('R:') for t in info['history'])
                             for info in allin.infos))
        # Enumerate each all-in terminal: no future betting or product runout array.
        values = [allin.terminal_utility(replace(called, phase='showdown', street=1, river=card), (0, 0))/100
                  for card in allin.legal_rivers[0, 0]]
        self.assertAlmostEqual(math.fsum(values)/44, 300*2/44-150)
        folded = allin.next_state(allin.next_state(State(), 'B:10000'), 'F')
        self.assertEqual(allin.terminal_utility(folded, (0, 0))/100, 50)

    def test_information_pooling_prevents_hidden_hand_and_future_peeking(self):
        config = copy.deepcopy(FIXTURES[5]['config'])
        # Retain strategic river choices: against a uniform policy in the
        # terminal-turn-only game, a root lead can make the cheat nondiscriminating.
        config['river_bet_sizes'] = [0.5]
        game = IndependentTurnGame(config)
        root = game.info_lookup[0, tuple(sorted(('Kh', 'Kd'))), ()]
        self.assertEqual(sum(record['info'] == root for record in game.records), 2)
        for card, count in (('As', 1), ('9c', 2)):
            info = game.info_lookup[0, tuple(sorted(('Kh', 'Kd'))), ('X', 'X', 'R:'+card)]
            self.assertEqual(sum(record['info'] == info for record in game.records), count)
        # Illegally maximize separately for each concrete hidden deal. This must
        # overstate the legal pooled best response against the uniform policy.
        profile = game.uniform.copy()
        probability = game.probabilities(profile)
        cheated = game.leaf_values.copy()
        for edge, parents, starts in reversed(game.layers):
            cheated[parents] = np.add.reduceat(probability[edge]*cheated[game.child[edge]], starts)
            for parent in parents[game.actor[parents] == 0]:
                cheated[parent] = max(cheated[game.records[parent]['children']])
        legal = game.evaluate(profile)['oop_upper_bound']
        self.assertGreater(cheated[0]/100-legal, 1)
        for record in game.records:
            if record['actor'] >= 0:
                history = game.infos[record['info']]['history']
                public_cards = [token for token in history if token.startswith('R:')]
                self.assertEqual(public_cards, [] if record['state'].street == 0 else ['R:'+record['state'].river])

    def test_analytic_singleton_minimax_and_training(self):
        game = IndependentTurnGame(FIXTURES[0]['config'])
        signs = [game.sign[0, 0, card] for card in game.legal_rivers[0, 0]]
        self.assertEqual((signs.count(1), signs.count(-1)), (16, 28))
        values = game.leaf_values.copy()
        probability = game.chance_probability
        for edge, parents, starts in reversed(game.layers):
            values[parents] = np.add.reduceat(probability[edge]*values[game.child[edge]], starts)
            for parent in parents:
                actor = game.actor[parent]
                if actor >= 0:
                    choices = values[game.records[parent]['children']]
                    values[parent] = max(choices) if actor == 0 else min(choices)
        self.assertAlmostEqual(values[0]/100, -300/11, places=10)
        trainer = IndependentCFR(game)
        checkpoints = trainer.train(1000)
        diagnostic = checkpoints[-1]
        self.assertLess(diagnostic['oop_lower_bound'], -300/11)
        self.assertGreater(diagnostic['oop_upper_bound'], -300/11)
        self.assertLess(diagnostic['nash_conv_chips'], checkpoints[0]['nash_conv_chips'])
        self.assertLess(diagnostic['nash_conv_chips'], 0.5)

    def test_independent_worker_and_bidirectional_policy_mapping(self):
        fixture = FIXTURES[3]
        result = compare_fixture(fixture, 500, 800)
        self.assertEqual(result['failures'], [], result['failures'])
        exported = result['reference_export']
        self.assertNotEqual(exported['pid'], os.getpid())
        self.assertEqual(exported['product_modules_loaded'], [])
        self.assertLess(result['same_policy_numeric_delta'], 1e-9)
        game = IndependentTurnGame(fixture['config'])
        expected = game.import_profile(exported['profile'])
        reordered = copy.deepcopy(exported['profile'])
        reordered.reverse()
        for row in reordered:
            row['actions'].reverse()
            row['probabilities'].reverse()
        np.testing.assert_array_equal(game.import_profile(reordered), expected)
        config = copy.deepcopy(fixture['config'])
        config['oop'].reverse()
        config['ip'].reverse()
        solver = product_solver(config)
        install_reference_profile(game, solver, expected)
        np.testing.assert_allclose(product_profile(game, solver), expected, atol=1e-14)
        for bad in (reordered[:-1], reordered+[reordered[0]]):
            with self.assertRaises(ValueError):
                game.import_profile(bad)
        solver.root.actions = ('check',)
        with self.assertRaises(ValueError):
            mapping(game, solver)

    def test_exact_hidden_hand_polarized_turn_equilibrium(self):
        # KK wins 2/44 versus AA and always versus QJ. With a pot-size shove,
        # KK calls 1/2 and QJ bets (1 - 3*(2/44))/2 = 19/44. AA always bets.
        game = IndependentTurnGame(FIXTURES[5]['config'])
        profile = game.uniform.copy()
        for index, info in enumerate(game.infos):
            hand, history = set(info['hand']), info['history']
            action = None
            if history == ():
                action = 'X'
            elif history == ('X',) and hand == {'As', 'Ad'}:
                action = 'B:10000'
            elif history == ('X',) and hand == {'Qh', 'Jd'}:
                profile[index] = 0
                profile[index, info['actions'].index('B:10000')] = 19/44
                profile[index, info['actions'].index('X')] = 25/44
            elif history == ('B:10000',):
                action = 'C' if hand == {'As', 'Ad'} else 'F'
            if action:
                profile[index] = 0
                profile[index, info['actions'].index(action)] = 1
        # Uniform at KK's fold/call information set is the required 1/2 mix.
        result = game.evaluate(profile)
        self.assertAlmostEqual(result['oop_ev'], -475/22, places=10)
        self.assertAlmostEqual(result['nash_conv_chips'], 0, places=10)

    def test_product_fault_is_detected_without_changing_reference(self):
        with patch('poker_spot.turn.rank7', return_value=(0,)):
            result = compare_fixture(FIXTURES[0], 100, 100)
        self.assertIn('Independent same-policy value/BR or reverse transfer differs', result['failures'])
        self.assertGreater(result['same_policy_numeric_delta'], 1)

    def test_invalid_inputs_and_future_rounding_are_rejected(self):
        base = FIXTURES[0]['config']
        for change in ({'max_raises': 1}, {'include_all_in': True}, {'pot': 100.001},
                       {'board': ['2c']*4}, {'stack': True}, {'river_bet_sizes': [0.333333333]},
                       {'turn_bet_sizes': [0.5, 0.5]}, {'oop': [{'hand': 'AsKs', 'weight': math.nan}]},
                       {'ip': [{'hand': 'AsKh', 'weight': 1}]}, {'oop': base['oop']*2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                IndependentTurnGame(base | change)
        with self.assertRaises(ValueError):
            IndependentCFR(IndependentTurnGame(base)).train(19)
        with self.assertRaises(subprocess.CalledProcessError) as error:
            independent_train(base, 19)
        self.assertEqual(error.exception.returncode, 2)


if __name__ == '__main__':
    unittest.main()
