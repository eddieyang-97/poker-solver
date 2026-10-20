import copy
import json
from pathlib import Path
import unittest

from poker_spot.history import HistoryError, parse_history, reconstruct, revise_hand

ROOT = Path(__file__).resolve().parents[1]
HAND = json.loads((ROOT/'examples/hand-review.json').read_text())


class HistoryTests(unittest.TestCase):
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
                       text+'Blinds: £2/£5\n', text+'Known UTG: Ad Kd\n'):
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


if __name__ == '__main__':
    unittest.main()
