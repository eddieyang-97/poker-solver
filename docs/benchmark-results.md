# Independent river benchmark

| Fixture | Root EV delta / pot | Local NashConv | Reference NashConv | Status |
| --- | --- | --- | --- | --- |
| polarized_pot | 0.00000091 | 0.037147 | 0.015041 | PASS |
| polarized_half | 0.00000022 | 0.018954 | 0.006402 | PASS |
| dry_merged | 0.00000062 | 0.002758 | 0.001232 | PASS |
| monotone | 0.00001110 | 0.003254 | 0.000798 | PASS |
| paired_blockers | 0.00000179 | 0.007541 | 0.002084 | PASS |
| four_flush | 0.00000462 | 0.000841 | 0.000122 | PASS |
| four_straight | 0.00000084 | 0.001956 | 0.002082 | PASS |
| board_tie | 0.00000002 | 0.000033 | 0.000005 | PASS |
| short_stack | 0.00000042 | 0.001205 | 0.000447 | PASS |
| sterling_multi_rare | 0.00000116 | 0.019752 | 0.003733 | PASS |

## Analytical polarized checks

Frequencies below are conditional on their decision nodes; EVs use the half-pot baseline.

| Fixture / engine | OOP root EV | QJ bet | KK call | OOP check |
| --- | --- | --- | --- | --- |
| polarized_pot / local | -25.00007147 | 50.005608% | 49.931648% | 99.999596% |
| polarized_pot / reference | -25.00000914 | 49.971236% | 49.998710% | 99.999943% |
| polarized_pot / analytical | -25.00000000 | 50.000000% | 50.000000% | 100% |
| polarized_half / local | -16.66674808 | 33.315392% | 66.706207% | 99.998820% |
| polarized_half / reference | -16.66667795 | 33.328516% | 66.682586% | 99.999834% |
| polarized_half / analytical | -16.66666667 | 33.333333% | 66.666667% | 100% |

## Discrepancies

No same-tree discrepancies exceeded the documented gates.
