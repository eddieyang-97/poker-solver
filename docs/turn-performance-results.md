# Maximum-dimension local turn performance

Maximum configured dimensions on two synthetic inputs, not a proof of worst runtime over all inputs. Resident-memory peaks include imports/native allocations; not address-space usage or an enforced memory cap. Timing and memory are observations, not portable performance acceptance thresholds.

| Fixture / repeat | Process seconds | Compute seconds | Peak resident MiB | NashConv % pot | Status |
| --- | --- | --- | --- | --- | --- |
| deep_dry_24x24 / 1 | 11.902 | 11.605 | 34.43 | 0.00094806 | COMPLETED |
| deep_dry_24x24 / 2 | 11.790 | 11.536 | 34.47 | 0.00094806 | COMPLETED |
| deep_dry_24x24 / 3 | 11.860 | 11.607 | 34.45 | 0.00094806 | COMPLETED |
| four_flush_weighted_24x24 / 1 | 12.152 | 11.898 | 33.63 | 0.00653338 | COMPLETED |
| four_flush_weighted_24x24 / 2 | 11.962 | 11.709 | 34.66 | 0.00653338 | COMPLETED |
| four_flush_weighted_24x24 / 3 | 11.922 | 11.667 | 33.75 | 0.00653338 | COMPLETED |

## Unresolved gates

No hosted timeout, address-space limit, concurrency, OAuth or ChatGPT turn acceptance was tested.
Convergence is reported, not used as a performance pass criterion.
