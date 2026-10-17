# Experimental local turn/river validation

Fresh CFR+ solves; scalar oracle reads the product tree and policy. No external turn trainer comparison.

| Fixture | OOP EV | NashConv | Oracle max delta | Seconds | Status |
| --- | --- | --- | --- | --- | --- |
| checkdown_known_outs | 2.27272727 | -0.00000000 | 4.44e-16 | 0.125 | PASS |
| turn_shove_dry | -21.59088842 | 0.01544831 | 1.42e-14 | 0.337 | PASS |
| two_street_dry | -48.63275926 | 0.01324362 | 3.68e-14 | 0.716 | PASS |
| spade_draw_two_sizes | -50.00121815 | 0.00193204 | 7.11e-15 | 1.630 | PASS |
| paired_short_stack | 16.71816053 | 0.03139926 | 3.55e-15 | 2.164 | PASS |
| four_flush | 49.99952153 | 0.00094812 | 3.95e-15 | 3.204 | PASS |
| weighted_shared_card | -37.47940831 | 0.00250059 | 2.37e-15 | 2.041 | PASS |
| duplicate_capped_shoves | -49.99981028 | 0.00055301 | 1.58e-14 | 0.909 | PASS |

## Discrepancies

No stated gate failed.
