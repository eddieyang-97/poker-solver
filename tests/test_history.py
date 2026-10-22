import copy
import json
from pathlib import Path
import unittest

from poker_spot.history import HistoryError, parse_history, reconstruct, revise_hand
from poker_spot.raises import RaiseRiverSolver

ROOT = Path(__file__).resolve().parents[1]
HAND = json.loads((ROOT/'examples/hand-review.json').read_text())


class HistoryTests(unittest.TestCase):
    def test_limp_call_check_raise_accounting_and_local_tree_boundary(self):
        # Synthetic 150bb accounting case; stacks/rake are test assumptions.
        parsed = parse_history('''Context: post-session
Currency: GBP
Blinds: 1/2
Stacks: 300 each
Players: UTG, HJ, CO, BTN, SB, BB
Rake: none
Dead money: 0
Preflop: UTG folds; HJ calls to 2; CO calls to 2; BTN raises to 10; SB folds; BB folds; HJ calls to 10; CO calls to 10
Flop Ac Jh 3s: HJ checks; CO checks; BTN bets 15; HJ calls; CO folds
Turn Tc: HJ checks; BTN checks
River 4c: HJ checks; BTN bets 40; HJ raises to 120; BTN calls
''')
        self.assertEqual(parsed['issues'], [])
        hand = parsed['hand']
        result = reconstruct(hand)
        self.assertEqual([s['pot_end'] for s in result['streets']], [33, 63, 63, 303])
        self.assertEqual(result['streets'][1]['action_order'], ['UTG+1', 'UTG+2', 'BTN'])
        river = result['streets'][-1]
        self.assertEqual(river['action_order'], ['UTG+1', 'BTN'])
        self.assertEqual(river['stacks_start'], {'UTG+1': 275, 'BTN': 275})
        self.assertEqual({p: river['stacks_end'][p] for p in river['players_end']}, {'UTG+1': 155, 'BTN': 155})
        pending = copy.deepcopy(hand)
        pending['streets'][-1]['actions'].pop()
        self.assertEqual(reconstruct(pending)['decision']['actor'], 'BTN')
        self.assertEqual(reconstruct(pending)['decision']['to_call'], 80)
        self.assertEqual(result['ledger'][-1]['paid'], 80)
        self.assertIsNone(result['decision']['actor'])
        # Constructor canaries only: these hands are not inferred arrival ranges.
        config = dict(board=result['board'], oop_range='KhKd', ip_range='QsQd',
                      pot=river['pot_start'], stack=river['effective_stack_heads_up'],
                      minimum_bet=2, bet_sizes=[0.5], raise_sizes=[0.5])
        solver = RaiseRiverSolver(**config)
        self.assertEqual((solver.pot_cents, solver.stack_cents), (6300, 27500))
        self.assertIn('raise_to_94.50', solver.nodes['c/b3150'].actions)
        # The current fraction-only API cannot encode the observed 40/63 exactly.
        # Keep its rounding rejection; exact observed sizing belongs to integration work.
        with self.assertRaisesRegex(ValueError, 'cent-exact'):
            RaiseRiverSolver(**dict(config, bet_sizes=[40/63]))

    def test_motivating_hand_and_prose(self):
        parsed = parse_history((ROOT/'examples/hand-review.txt').read_text(encoding='utf-8'))
        self.assertEqual(parsed['issues'], [])
        for hand in (HAND, parsed['hand']):
            r = reconstruct(hand)
            self.assertEqual([s['pot_start'] for s in r['streets']], [3, 57, 87, 87])
            self.assertEqual(r['streets'][1]['players_start'], ['UTG', 'UTG+1', 'UTG+2'])
            self.assertEqual(r['streets'][2]['players_start'], ['UTG', 'UTG+2'])
            self.assertEqual(r['decision']['street_start']['effective_stack_heads_up'], 367)
            self.assertEqual(r['decision']['actor'], 'UTG')
            self.assertEqual(r['decision']['to_call'], 40)
            self.assertAlmostEqual(r['decision']['required_equity'], 40/167)
            self.assertEqual(sum(p['gross_amount'] for p in r['pot_layers_gross_before_rake']), 127)
            self.assertEqual({row['kind'] for row in r['ledger']}, {'provided_fact', 'computed_reconstruction'})

    def test_antes_dead_money_fixed_and_percentage_rake(self):
        hand = copy.deepcopy(HAND)
        hand['forced_posts'] += [dict(player=p['position'], kind='ante', amount=0.2) for p in hand['players']]
        hand['dead_money'] = 5
        self.assertEqual(reconstruct(hand)['streets'][1]['pot_start'], 63.2)
        hand['rake'] = {'model': 'fixed', 'amount': 5, 'street': 'flop'}
        r = reconstruct(hand)
        self.assertEqual(r['streets'][1]['pot_start'], 58.2)
        self.assertEqual(r['streets'][3]['pot_start'], 88.2)
        self.assertEqual(r['decision']['street_start']['effective_stack_heads_up'], 366.8)
        hand['rake'] = {'model': 'percentage', 'rate': 0.05, 'cap': 3, 'street': 'river', 'rounding': 'floor_cent'}
        self.assertEqual(reconstruct(hand)['streets'][3]['pot_start'], 90.2)
        for rake in (None, {'model': 'unknown'}, {'model': 'percentage', 'rate': 0.05, 'cap': 3, 'street': 'river'}):
            hand['rake'] = rake
            with self.assertRaises(HistoryError):
                reconstruct(hand)

    def test_total_to_calls_and_corrections(self):
        hand = revise_hand(HAND, '/streets/0/actions/6', {'player': 'UTG', 'action': 'call', 'to': 18})
        self.assertEqual(reconstruct(hand)['streets'][1]['pot_start'], 57)
        self.assertEqual(HAND['streets'][0]['actions'][6]['amount'], 12)
        bad = revise_hand(HAND, '/streets/0/actions/6/amount', 18)
        with self.assertRaises(HistoryError):
            reconstruct(bad)
        with self.assertRaises(HistoryError):
            revise_hand(HAND, '/players/99/stack', 1)
        corrected = revise_hand(HAND, '/players/0/stack', 500)
        self.assertEqual(reconstruct(corrected)['decision']['street_start']['stacks_start']['UTG'], 467)

    def test_order_stack_and_card_inconsistencies_rejected(self):
        bads = [revise_hand(HAND, '/streets/1/actions/0/player', 'UTG+1'),
                revise_hand(HAND, '/players/0/stack', 20),
                revise_hand(HAND, '/streets/3/cards/0', 'Ac'),
                revise_hand(HAND, '/players/0/hole_cards/0', 'Ac'),
                revise_hand(HAND, '/dead_money', -1),
                revise_hand(HAND, '/context', 'live'),
                revise_hand(HAND, '/streets/0/actions/2/to', 7)]
        for bad in bads:
            with self.subTest(hand=bad), self.assertRaises(HistoryError):
                reconstruct(bad)
        with self.assertRaises(HistoryError):
            reconstruct(dict(HAND, verified=True))

    def test_short_allin_call_refund_and_forced_runout(self):
        hand = revise_hand(HAND, '/players/0/stack', 20)
        hand['streets'][1]['actions'][3] = {'player': 'UTG', 'action': 'call', 'amount': 2, 'all_in': True}
        hand['streets'][2]['actions'] = []
        hand['streets'][3]['actions'] = []
        r = reconstruct(hand)
        self.assertEqual(r['streets'][2]['pot_start'], 61)
        self.assertEqual(r['streets'][3]['pending'], [])
        self.assertEqual([e['amount'] for e in r['ledger'] if e.get('event') == 'uncalled_refund'], [13])
        self.assertEqual(sum(p['gross_amount'] for p in r['pot_layers_gross_before_rake']), 61)

    def test_short_raise_does_not_reopen_but_cumulative_full_raise_does(self):
        hand = copy.deepcopy(HAND)
        hand['players'][2]['stack'] = 8
        hand['streets'] = hand['streets'][:1]
        hand['streets'][0]['actions'][2] = {'player': 'UTG+2', 'action': 'raise', 'to': 8, 'all_in': True}
        hand['streets'][0]['actions'][6] = {'player': 'UTG', 'action': 'raise', 'to': 18}
        with self.assertRaisesRegex(HistoryError, 'not reopened'):
            reconstruct(hand)
        hand['players'][3]['stack'] = 10
        hand['streets'][0]['actions'][3] = {'player': 'BTN', 'action': 'raise', 'to': 10, 'all_in': True}
        r = reconstruct(hand)
        self.assertEqual(r['streets'][0]['pot_end'], 57)
        self.assertEqual(len(r['decision']['players']), 4)
        self.assertNotIn('required_equity', r['decision'])

    def test_partial_street_cannot_advance_and_multiplayer_odds_not_invented(self):
        hand = copy.deepcopy(HAND)
        hand['streets'][0]['actions'].pop()
        with self.assertRaisesRegex(HistoryError, 'still owes'):
            reconstruct(hand)
        hand = copy.deepcopy(HAND)
        hand['streets'][1]['actions'][-1] = {'player': 'UTG+1', 'action': 'call', 'amount': 15}
        hand['streets'][2]['actions'].insert(1, {'player': 'UTG+1', 'action': 'check'})
        hand['streets'][3]['actions'].insert(1, {'player': 'UTG+1', 'action': 'check'})
        r = reconstruct(hand)
        self.assertEqual(len(r['decision']['players']), 3)
        self.assertNotIn('required_equity', r['decision'])

    def test_effective_call_caps_and_uncalled_excess(self):
        r = reconstruct(revise_hand(HAND, '/players/0/stack', 50))
        self.assertEqual(r['decision']['to_call'], 17)
        self.assertEqual(r['decision']['uncalled_excess_if_call'], 23)
        self.assertEqual(r['decision']['pot_contested_if_call'], 104)
        self.assertAlmostEqual(r['decision']['required_equity'], 17/121)

    def test_prose_ambiguity_missing_details_and_unknown_lines_preserved(self):
        text = (ROOT/'examples/hand-review.txt').read_text(encoding='utf-8')
        for change in (text.replace('3-bets to', '3-bets'), text.replace('Rake: none\n', ''),
                       text+'Opponent is probably weak\n', text.replace('Blinds: £1/£2\n', ''),
                       text+'Blinds: £2/£5\n', text+'Known UTG: Ad Kd\n',
                       text.replace('200bb each', '200bb effective')):
            parsed = parse_history(change)
            self.assertEqual(parsed['status'], 'needs_clarification')
            self.assertTrue(parsed['issues'])

    def test_physical_seats_validate_clockwise_positions(self):
        hand = copy.deepcopy(HAND)
        for row, seat in zip(hand['players'], (4, 5, 6, 1, 2, 3), strict=True):
            row['seat'] = seat
        self.assertEqual(reconstruct(hand)['streets'][1]['pot_start'], 57)
        for seats in ((4, 5, 6, 1, 3, 2), (4, 5, 6, 1, 2, 2)):
            for row, seat in zip(hand['players'], seats, strict=True):
                row['seat'] = seat
            with self.assertRaises(HistoryError):
                reconstruct(hand)
        for pointer in ('/players/-1/stack', '/players/01/stack'):
            with self.assertRaises(HistoryError):
                revise_hand(HAND, pointer, 1)

    def test_check_before_short_allin_can_raise(self):
        hand = copy.deepcopy(HAND)
        hand['streets'] = hand['streets'][:2]
        hand['players'][2]['stack'] = 19
        hand['streets'][1]['actions'] = [
            {'player': 'UTG', 'action': 'check'}, {'player': 'UTG+1', 'action': 'check'},
            {'player': 'UTG+2', 'action': 'bet', 'amount': 1, 'all_in': True},
            {'player': 'UTG', 'action': 'raise', 'to': 3}]
        r = reconstruct(hand)
        self.assertEqual(r['decision']['actor'], 'UTG+1')
        self.assertEqual(r['decision']['to_call'], 3)

    def test_short_allin_blinds_close_at_actual_contestable_wager(self):
        for small_stack, big_stack, ante in ((100, 1, 0), (100, 1.5, 0), (0.5, 1, 0), (0.5, 100, 0), (100, 1.2, 0.2)):
            with self.subTest(small=small_stack, big=big_stack, ante=ante):
                hand = copy.deepcopy(HAND)
                hand['players'] = [{'position': 'SB', 'stack': small_stack}, {'position': 'BB', 'stack': big_stack}]
                hand['forced_posts'] = []
                if ante:
                    hand['forced_posts'] = [{'player': p, 'kind': 'ante', 'amount': ante} for p in ('SB', 'BB')]
                small_post = min(1, round(small_stack-ante, 2))
                big_post = min(2, round(big_stack-ante, 2))
                hand['forced_posts'] += [{'player': 'SB', 'kind': 'small_blind', 'amount': small_post},
                                         {'player': 'BB', 'kind': 'big_blind', 'amount': big_post}]
                actions = ([{'player': 'SB', 'action': 'call', 'amount': big_post-small_post}]
                           if big_post > small_post and small_stack > small_post+ante else [])
                if actions:
                    partial = copy.deepcopy(hand)
                    partial['streets'] = [{'name': 'preflop', 'cards': [], 'actions': []}]
                    d = reconstruct(partial)['decision']
                    self.assertEqual(d['to_call'], big_post-small_post)
                    self.assertAlmostEqual(d['required_equity'], (big_post-small_post)/(2*(big_post+ante)))
                    partial['streets'][0]['actions'] = [{'player': 'SB', 'action': 'raise', 'to': 4}]
                    with self.assertRaisesRegex(HistoryError, 'no opponent can contest'):
                        reconstruct(partial)
                for street in hand['streets']:
                    street['actions'] = actions if street['name'] == 'preflop' else []
                r = reconstruct(hand)
                self.assertTrue(all(not s['pending'] for s in r['streets']))
                self.assertEqual(r['decision']['to_call'], 0)
                self.assertNotIn('required_equity', r['decision'])
                self.assertAlmostEqual(r['decision']['pot_current'], 2*min(small_stack, big_stack))

    def test_nominal_blind_is_preserved_until_only_one_stack_can_bet(self):
        hand = copy.deepcopy(HAND)
        hand['players'] = [{'position': 'UTG', 'stack': 100}, {'position': 'SB', 'stack': 100}, {'position': 'BB', 'stack': 1}]
        hand['forced_posts'][1]['amount'] = 1
        hand['streets'] = hand['streets'][:1]
        hand['streets'][0]['actions'] = []
        r = reconstruct(hand)
        self.assertEqual(r['decision']['to_call'], 2)
        hand['streets'][0]['actions'] = [{'player': 'UTG', 'action': 'fold'}]
        r = reconstruct(hand)
        self.assertEqual(r['decision']['actor'], None)
        self.assertEqual(r['decision']['to_call'], 0)
        hand['streets'][0]['actions'] = [{'player': 'UTG', 'action': 'call', 'amount': 2}]
        self.assertEqual(reconstruct(hand)['decision']['to_call'], 1)
        hand['streets'][0]['actions'] = [{'player': 'UTG', 'action': 'raise', 'to': 3}]
        with self.assertRaisesRegex(HistoryError, 'Under-minimum'):
            reconstruct(hand)
        hand['streets'][0]['actions'] = [{'player': 'UTG', 'action': 'raise', 'to': 4}]
        self.assertEqual(reconstruct(hand)['decision']['to_call'], 3)


if __name__ == '__main__':
    unittest.main()
