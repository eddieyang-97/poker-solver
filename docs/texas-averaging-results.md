# TexasSolver controlled averaging experiment

Independent evaluation of separately identified source-build policies. The unmodified release failures remain recorded separately.

| Variant | Completed iterations | OOP average EV | Average NashConv | Current NashConv | Source/average gap delta | Average status |
| --- | --- | --- | --- | --- | --- | --- |
| baseline_observer | 4,000 | -24.97470416 | 1.59073955 | 2.51022398 | 0.00002164 | FAIL |
| baseline_observer | 8,000 | -25.01984729 | 1.43077600 | 1.88241291 | 0.00000823 | FAIL |
| baseline_observer | 12,000 | -25.01130341 | 1.28588313 | 2.17821854 | 0.00000173 | FAIL |
| baseline_observer | 16,000 | -24.99262981 | 1.17590821 | 2.23949683 | 0.00000107 | FAIL |
| baseline_observer | 20,000 | -25.01005819 | 1.16607809 | 1.97325766 | 0.00000715 | FAIL |
| baseline_observer | 24,000 | -24.97837887 | 1.41035521 | 1.43725157 | 0.00000823 | FAIL |
| baseline_observer | 28,000 | -25.00851339 | 1.15222907 | 2.00462747 | 0.00000358 | FAIL |
| baseline_observer | 32,000 | -25.01483820 | 1.28761464 | 1.70748091 | 0.00001699 | FAIL |
| baseline_observer | 36,000 | -25.00438031 | 1.06424439 | 1.86635327 | 0.00000679 | FAIL |
| baseline_observer | 40,000 | -25.00777017 | 1.13173461 | 1.77262557 | 0.00000167 | FAIL |
| theta_one | 4,000 | -24.99999894 | 0.00335872 | 2.51022398 | 0.00000012 | PASS |
| theta_one | 8,000 | -24.99999960 | 0.00070280 | 1.88241291 | 0.00001818 | PASS |
| theta_one | 12,000 | -24.99999928 | 0.00078952 | 2.17821854 | 0.00000179 | PASS |
| theta_one | 16,000 | -25.00000071 | 0.00074303 | 2.23949683 | 0.00001442 | PASS |
| theta_one | 20,000 | -25.00000294 | 0.00123239 | 1.97325766 | 0.00000405 | PASS |
| theta_one | 24,000 | -25.00000071 | 0.00094593 | 1.43725157 | 0.00000751 | PASS |
| theta_one | 28,000 | -24.99999970 | 0.00101781 | 2.00462747 | 0.00001264 | PASS |
| theta_one | 32,000 | -25.00000072 | 0.00018311 | 1.70748091 | 0.00000381 | PASS |
| theta_one | 36,000 | -24.99999633 | 0.00035620 | 1.86635327 | 0.00000620 | PASS |
| theta_one | 40,000 | -24.99999705 | 0.00005794 | 1.77262557 | 0.00000882 | PASS |

Unchanged convergence gate: 0.50 chips.

Maximum sampled current-policy difference between variants: 0.

Averaging effect observed with matching sampled current policies: True.

This is one fixture and one controlled change, not a general fix or reference acceptance.
