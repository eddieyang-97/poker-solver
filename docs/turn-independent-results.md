# Independently trained small turn/river games

In-repository development reference, not an externally audited solver or gold standard

| Fixture | Product EV | Reference EV | Product gap | Reference gap | Same-policy max delta | Status |
| --- | --- | --- | --- | --- | --- | --- |
| singleton_minimax | -27.27301750 | -27.27279985 | 0.00044952 | 0.00011241 | 1.42e-14 | PASS |
| weighted_dry | -48.63323199 | -48.63335220 | 0.00527675 | 0.00267775 | 6.9e-14 | PASS |
| draw_two_sizes | -50.00030469 | -50.00007619 | 0.00048325 | 0.00012084 | 1.42e-14 | PASS |
| weighted_collision | -37.47935623 | -37.47934320 | 0.00047676 | 0.00020344 | 1.42e-14 | PASS |
| paired_capped | 19.33325383 | 19.33331345 | 0.00010761 | 0.00002691 | 1.56e-14 | PASS |
| turn_allin | -21.59093993 | -21.59092071 | 0.02218518 | 0.01583623 | 1.07e-14 | PASS |
| weighted_4x4_collision | -26.78880172 | -26.78863481 | 0.00382528 | 0.00163083 | 2.13e-14 | PASS |
| four_flush_4x4 | 21.81260783 | 21.81258375 | 0.00167046 | 0.00050065 | 2.49e-14 | PASS |
| trips_3x4 | 35.02643226 | 35.02894981 | 0.00949695 | 0.00371658 | 1.42e-14 | PASS |
| draw_4x4_two_sizes | 47.92304699 | 47.92320534 | 0.00144818 | 0.00057214 | 2.84e-14 | PASS |

## Discrepancies

No declared gate failed. General full-game GTO and hosted turn acceptance are not established.
