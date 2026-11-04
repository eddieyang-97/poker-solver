import unittest

from poker_spot.validation import InputError, calculate, validate


class InputFormatsTest(unittest.TestCase):
    def setUp(self):
        self.solve = dict(board='Th,As,Td,9h,8d', oop_range='Ad5d,AA,AKs,AKo,AQs,KK,QQ',
                          ip_range='AhKd,AA,AKs,AKo,AQs,KK,QQ,QJs', pot=166800,
                          stack=400000, bet_sizes=[0.3], oop_hand='Ad5d', ip_hand='AhKd', iterations=100)

    def test_equivalent_solve_inputs(self):
        baseline = validate('solve_river', self.solve, hosted=True)
        expected = calculate('solve_river', self.solve)
        for board in ('ThAsTd9h8d', 'Th As Td 9h 8d'):
            variant = dict(self.solve, board=board, oop_hand='Ad 5d', ip_hand='Ah Kd',
                           oop_range='Ad5d, AA, AKs, AKo, AQs, KK, QQ')
            self.assertEqual(validate('solve_river', variant, hosted=True), baseline)
            self.assertEqual(calculate('solve_river', variant), expected)

    def test_call_and_weight_whitespace(self):
        args = dict(board='ThAsTd9h8d', hero_hand='Ad 5d', villain_betting_range='AhKd: 0.5, QQ', pot=100, bet=20)
        other = dict(args, board='Th As Td 9h 8d', hero_hand='Ad5d', villain_betting_range='AhKd:0.5,QQ')
        self.assertEqual(calculate('evaluate_river_call', args), calculate('evaluate_river_call', other))

    def test_actionable_errors(self):
        cases = [('board', 'ThAsTd9hXx', 'invalid_card'), ('board', 'ThAsTd9h', 'card_count'),
                 ('board', 'ThAsTd9hTh', 'duplicate_card'), ('oop_hand', 'Th5d', 'board_conflict'),
                 ('oop_range', 'AKs:2', 'invalid_weight'), ('bet_sizes', [0.3, 0.3], 'invalid_sizing'),
                 ('iterations', 1501, 'hosted_limit')]
        for field, value, reason in cases:
            with self.subTest(field=field, value=value), self.assertRaises(InputError) as err:
                validate('solve_river', dict(self.solve, **{field: value}), hosted=True)
            self.assertEqual(err.exception.details['reason'], reason)
            self.assertEqual(err.exception.details['field'], field)


if __name__ == '__main__':
    unittest.main()
