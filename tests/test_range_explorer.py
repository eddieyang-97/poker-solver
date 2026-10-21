import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from poker_spot.history import HistoryError
from poker_spot.range_explorer import explore, probability, render_markdown
from scripts.benchmark_range_explorer import maximum_case
from scripts.explore_ranges import execute, read_json

ROOT = Path(__file__).resolve().parents[1]
HAND = json.loads((ROOT/'examples/hand-review.json').read_text())
MODELS = json.loads((ROOT/'examples/range-models.json').read_text())


def key(text):
    return ''.join(sorted((text[:2], text[2:]), key=lambda c: '23456789TJQKA'.index(c[0])*4+'cdhs'.index(c[1])))


def fraction_oracle(spec, board):
    """Separate small-fixture enumeration using exact rational input arithmetic."""
    priors = {}
    for player, prior in spec['priors'].items():
        rows = {}
        for token in prior['range'].split(','):
            combo, _, weight = token.partition(':')
            rows[key(combo)] = Fraction(weight or '1')
        priors[player] = rows
    players = list(priors)
    marginals = {p: dict.fromkeys(priors[p], Fraction(0)) for p in players}
    joint = {}
    mass = Fraction(0)
    for hands in itertools.product(*priors.values()):
        private = [c for h in hands for c in (h[:2], h[2:])]
        if len(set(private)) != len(private) or set(private) & set(board):
            continue
        w = Fraction(1)
        for p, h in zip(players, hands, strict=True):
            w *= priors[p][h]
        for model in spec['profiles'][0]['models']:
            # This fixture's two events are UTG opening and UTG+1 folding.
            actor, observed = ('UTG', 'open6') if model['street'] == 'preflop' else ('UTG+1', 'fold')
            h = hands[players.index(actor)]
            row = next(v for c, v in model['frequencies'].items() if key(c) == h)
            w *= Fraction(str(row[observed]))
        mass += w
        for p, h in zip(players, hands, strict=True):
            marginals[p][h] += w
        pair = '|'.join(hands[players.index(p)] for p in spec['target_pair'])
        joint[pair] = joint.get(pair, Fraction(0))+w
    return {p: {h: w/mass for h, w in rows.items()} for p, rows in marginals.items()}, {h: w/mass for h, w in joint.items()}


class RangeExplorerTests(unittest.TestCase):
    def test_analytical_posterior_and_marginal_export_is_not_equivalent(self):
        model = copy.deepcopy(MODELS)
        del model['priors']['UTG+1']
        model['through'] = {'street': 'preflop', 'index': 0}
        model['profiles'] = [model['profiles'][0]]
        model['profiles'][0]['models'] = model['profiles'][0]['models'][:1]
        r = explore(HAND, model)['profiles'][0]
        self.assertAlmostEqual(float(r['marginals_decimal']['UTG']['AdAs']), 2/3)
        self.assertAlmostEqual(float(r['marginals_decimal']['UTG+2'][key('AsQc')]), 1/6)
        self.assertEqual(Decimal(r['trace'][0]['conditional_action_probability_decimal']), Decimal('.4'))
        self.assertAlmostEqual(float(r['independent_marginal_export_tv_decimal']), 7/48)

    def test_folded_player_remains_latent_and_exact_fraction_enumeration(self):
        spec = copy.deepcopy(MODELS)
        spec['profiles'] = [spec['profiles'][0]]
        spec['profiles'][0]['models'] = spec['profiles'][0]['models'][1:]
        result = explore(HAND, spec)
        r = result['profiles'][0]
        self.assertEqual(result['solver_execution'], 'not_run')
        self.assertAlmostEqual(float(r['marginals_decimal']['UTG']['AdAs']), 1/13)
        self.assertAlmostEqual(float(r['marginals_decimal']['UTG+2'][key('AsQc')]), 11/13)
        self.assertEqual(Decimal(r['trace'][-1]['conditional_action_probability_decimal']), Decimal('.325'))
        expected, joint = fraction_oracle(spec, result['board'])
        for p, rows in expected.items():
            for h, w in rows.items():
                self.assertAlmostEqual(float(r['marginals_decimal'][p][h]), float(w), places=14)
        for h, w in joint.items():
            self.assertAlmostEqual(float(r['target_pair_joint_decimal'].get(h, '0')), float(w), places=14)
        del spec['priors']['UTG+1']
        spec['profiles'][0]['models'] = []
        dropped = explore(HAND, spec)['profiles'][0]
        self.assertAlmostEqual(float(dropped['marginals_decimal']['UTG']['AdAs']), 1/3)

    def test_twenty_random_models_against_exact_fraction_oracle(self):
        rng = random.Random(1102)
        for _ in range(20):
            spec = copy.deepcopy(MODELS)
            spec['profiles'] = [spec['profiles'][0]]
            for m in spec['profiles'][0]['models']:
                for row in m['frequencies'].values():
                    p = rng.randint(1, 9)
                    a, b = row
                    row[a], row[b] = p/10, (10-p)/10
            result = explore(HAND, spec)
            expected, joint = fraction_oracle(spec, result['board'])
            actual = result['profiles'][0]
            for player, rows in expected.items():
                for h, w in rows.items():
                    self.assertAlmostEqual(float(actual['marginals_decimal'][player][h]), float(w), places=14)
            for h, w in joint.items():
                self.assertAlmostEqual(float(actual['target_pair_joint_decimal'].get(h, '0')), float(w), places=14)

    def test_future_cards_actions_and_hole_card_reveals_do_not_condition_prefix(self):
        spec = copy.deepcopy(MODELS)
        spec['through'] = {'street': 'preflop', 'index': 0}
        spec['profiles'] = [dict(id='unknown', description='Unknown actions', models=[])]
        spec['priors']['UTG']['range'] = 'AcAd,KhKd'
        first = explore(HAND, spec)
        changed = copy.deepcopy(HAND)
        changed['players'][0].update(hole_cards=['2c', '2d'], knowledge='hero')
        changed['players'][2].update(hole_cards=['Qs', 'Qd'], knowledge='showdown')
        changed['streets'][1]['cards'] = ['As', '7s', '6s']
        changed['streets'][3]['actions'] = [{'nonsense': 'outside selected prefix'}]
        self.assertEqual(first, explore(changed, spec))
        self.assertGreater(Decimal(first['profiles'][0]['marginals_decimal']['UTG']['AcAd']), 0)
        spec['through'] = MODELS['through']
        later = explore(HAND, spec)
        self.assertEqual(Decimal(later['profiles'][0]['marginals_decimal']['UTG']['AcAd']), 0)
        self.assertEqual(later['profiles'][0]['gaps'][0]['reason'], 'Unknown action likelihood; no update')

    def test_common_scaling_tiny_decimal_models_and_ambient_context(self):
        first = explore(HAND, MODELS)
        scaled = copy.deepcopy(MODELS)
        for prior in scaled['priors'].values():
            prior['range'] = ','.join(t+':1e-200' for t in prior['range'].split(','))
        second = explore(HAND, scaled)
        for a, b in zip(first['profiles'], second['profiles'], strict=True):
            self.assertEqual(a['marginals_decimal'], b['marginals_decimal'])
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(first, explore(HAND, MODELS))
        tiny = copy.deepcopy(MODELS)
        tiny['profiles'] = [tiny['profiles'][0]]
        complement = '0.'+'9'*200
        for row in tiny['profiles'][0]['models'][0]['frequencies'].values():
            row.update(fold=complement, open6='1e-200')
        result = explore(HAND, tiny)['profiles'][0]
        self.assertEqual(Decimal(result['trace'][0]['conditional_action_probability_decimal']), Decimal('1e-200'))
        self.assertTrue(all(Decimal(w) > 0 for rows in result['marginals_decimal'].values() for w in rows.values()))
        for value in ('1e-301', 'NaN', True, 1.1, -1, float('inf'), 10**500):
            with self.subTest(value=str(value)), self.assertRaises(HistoryError):
                probability(value)

    def test_zero_probability_is_impossible_and_baseline_not_comparable(self):
        spec = copy.deepcopy(MODELS)
        for row in spec['profiles'][0]['models'][0]['frequencies'].values():
            row.update(fold=1, open6=0)
        result = explore(HAND, spec)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['profiles'][0]['status'], 'impossible_observation')
        self.assertTrue(all(p['sensitivity']['status'] == 'not_comparable' for p in result['profiles']))
        self.assertNotIn('marginals_decimal', result['profiles'][0])
        self.assertIn('zero probability', render_markdown(result))

    def test_model_binding_legal_alternatives_rows_and_dimension_rejection(self):
        variants = []
        for field, value in [('index', True), ('index', 99), ('provenance', ''),
                             ('alternatives', [{'id': 'bad', 'action': 'check'}])]:
            spec = copy.deepcopy(MODELS)
            spec['profiles'][0]['models'][0][field] = value
            variants.append(spec)
        spec = copy.deepcopy(MODELS)
        spec['profiles'][0]['models'][0]['alternatives'][1]['to'] = 5
        variants.append(spec)  # legal raise, wrong observed amount
        for row in ({'fold': .1, 'open6': .1}, {'fold': 1, 'open6': '1e-200'}, {'fold': True, 'open6': 0}, {'fold': 1}):
            spec = copy.deepcopy(MODELS)
            spec['profiles'][0]['models'][0]['frequencies']['AsAd'] = row
            variants.append(spec)
        spec = copy.deepcopy(MODELS)
        del spec['profiles'][0]['models'][0]['frequencies']['AsAd']
        variants.append(spec)
        spec = copy.deepcopy(MODELS)
        spec['priors']['UTG']['range'] = 'AK,AQ'
        variants.append(spec)
        spec = copy.deepcopy(MODELS)
        spec['profiles'][0]['models'] *= 2
        variants.append(spec)
        spec = copy.deepcopy(MODELS)
        spec['profiles'][1]['id'] = spec['profiles'][0]['id']
        variants.append(spec)
        for spec in variants:
            with self.subTest(spec=spec), self.assertRaises(HistoryError):
                explore(HAND, spec)

    def test_actual_worker_timeout_cli_edit_and_evidence_labels(self):
        result = execute(HAND, MODELS)
        self.assertEqual(result['status'], 'computed', result)
        self.assertEqual(result['solver_execution'], 'not_run')
        self.assertEqual(len(result['source_sha256_lf']), 5)
        self.assertIn('Solver execution: not run', render_markdown(result))
        self.assertNotIn('action_ev', json.dumps(result))
        self.assertEqual(execute(HAND, MODELS, timeout=.001)['error']['code'], 'TIMEOUT')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'edited'
            command = [sys.executable, str(ROOT/'scripts/explore_ranges.py'), str(ROOT/'examples/hand-review.json'),
                       '--models', str(ROOT/'examples/range-models.json'), '--set', '/through/index=3',
                       '--output', str(out)]
            # A model for a now-future action must be rejected, not silently ignored.
            child = subprocess.run(command, capture_output=True, timeout=20)
            self.assertEqual(child.returncode, 2)
            self.assertEqual(json.loads(out.with_suffix('.json').read_text())['status'], 'not_run')
            self.assertIn('Solver execution: not run', out.with_suffix('.md').read_text())
            command = command[:command.index('--set')]+['--set', '/profiles/0/description="Edited model"', '--output', str(out)]
            child = subprocess.run(command, capture_output=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(json.loads(out.with_suffix('.json').read_text())['profiles'][0]['description'], 'Edited model')
            out.with_suffix('.json').write_text('{"duplicate":1,"duplicate":2}')
            with self.assertRaises(ValueError):
                read_json(out.with_suffix('.json'))
            out.with_suffix('.json').write_text(' '*262145)
            with self.assertRaises(ValueError):
                read_json(out.with_suffix('.json'))

    def test_maximum_shape_and_remaining_structural_rejections(self):
        hand, model = maximum_case(False)
        result = explore(hand, model)
        self.assertTrue(all(p['initial_compatible_deals'] == 24**3 for p in result['profiles']))
        self.assertTrue(all(len(p['trace']) == 24 for p in result['profiles']))
        self.assertTrue(all(len(rows) == 24 for p in result['profiles'] for rows in p['marginals_decimal'].values()))
        self.assertTrue(all(float(p['independent_marginal_export_tv_decimal']) < 1e-14 for p in result['profiles']))
        for change in ('duplicate_combo', 'duplicate_action', 'too_many_models', 'too_many_profiles', 'too_many_players', 'underflow', 'no_deal'):
            spec = copy.deepcopy(MODELS)
            model = spec['profiles'][0]['models'][0]
            if change == 'duplicate_combo':
                model['frequencies']['AdAs'] = model['frequencies']['AsAd']
            elif change == 'duplicate_action':
                model['alternatives'].append(dict(id='samefold', action='fold'))
            elif change == 'too_many_models':
                spec['profiles'][0]['models'] = [model]*25
            elif change == 'too_many_profiles':
                spec['profiles'] *= 2
            elif change == 'too_many_players':
                spec['priors']['BTN'] = spec['priors']['UTG']
            elif change == 'underflow':
                spec['priors']['UTG']['range'] = 'AsAd:1e-324,KhKd'
            else:
                for prior in spec['priors'].values():
                    prior['range'] = 'AsAd'
                spec['profiles'] = [dict(id='no_deal', description='Incompatible private priors', models=[])]
            with self.subTest(change=change), self.assertRaises(HistoryError):
                explore(HAND, spec)
        with self.assertRaises(HistoryError):
            explore(dict(HAND, context='live'), MODELS)


if __name__ == '__main__':
    unittest.main()
