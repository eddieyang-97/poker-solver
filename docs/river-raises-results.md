# Local river raises: independent validation

Actual independent finite-tree river raise validation, local only; not full-game GTO or hosted acceptance

| Fixture | Product EV | Reference EV | Product gap | Reference gap | Max same-policy delta | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| polarized_half | -16.66674454 | -16.66668682 | 0.011851 | 0.008517 | 2.84e-14 | PASS |
| symmetric_value_air | -0.00004928 | -0.00001223 | 0.000677 | 0.000127 | 2.84e-14 | PASS |
| weighted_blockers | 15.54620864 | 15.54620106 | 0.002343 | 0.002131 | 8.76e-09 | PASS |
| short_allin_raise | -1.17190914 | -1.17188356 | 0.000435 | 0.000177 | 3.55e-14 | PASS |
| two_sizes | -2.34373742 | -2.34374737 | 0.003044 | 0.002276 | 1.14e-13 | PASS |
| paired_board | 6.99864143 | 6.99851578 | 0.008784 | 0.005312 | 4.26e-14 | PASS |
| flush_board | 15.15153928 | 15.15151481 | 0.016081 | 0.005616 | 2.84e-14 | PASS |
| allin_opening | -0.00000138 | -0.00000357 | 0.000627 | 0.000314 | 1.46e-14 | PASS |

## Measured maximum local workloads

- 2c,3d,4h,8s,9c: 3.822s parent wall, 3.438s CPU, 27.00 MiB peak resident; 13495 output bytes; NashConv 0.0006.
- Ks,9s,5h,Td,Ts: 3.705s parent wall, 3.344s CPU, 26.61 MiB peak resident; 13477 output bytes; NashConv 0.0005.

These are measured samples, not universal bounds or hosted acceptance.

## Discrepancies

No declared gate failed. Input ranges and omitted actions remain model assumptions.

Measured on Windows 11, Python 3.14.8, OPENBLAS_NUM_THREADS=1.
Product: 2,000 iterations; isolated pinned reference: 4,000 iterations.
Full profiles remain in local/CI artifacts; the versioned JSON retains their hashes.
48 seeded fully mixed policies also passed the unchanged 1e-8 gate.
The 8.76e-9 conditional-Q discrepancy is documented in the guide and JSON.
