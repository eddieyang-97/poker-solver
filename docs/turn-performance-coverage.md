# Maximum-dimension local turn performance

Maximum configured dimensions on two synthetic inputs, not a proof of worst runtime over all inputs. Resident-memory peaks include imports/native allocations; not address-space usage or an enforced memory cap. Timing and memory are observations, not portable performance acceptance thresholds.

| Fixture / repeat | Process seconds | Compute seconds | Peak resident MiB | NashConv % pot | Status |
| --- | --- | --- | --- | --- | --- |
| deep_dry_24x24 / 1 | 12.197 | 11.814 | 34.48 | 0.00094806 | COMPLETED |
| deep_dry_24x24 / 2 | 12.945 | 12.568 | 34.09 | 0.00094806 | COMPLETED |
| deep_dry_24x24 / 3 | 12.030 | 11.647 | 34.82 | 0.00094806 | COMPLETED |
| four_flush_weighted_24x24 / 1 | 12.191 | 11.795 | 34.51 | 0.00653338 | COMPLETED |
| four_flush_weighted_24x24 / 2 | 12.441 | 12.057 | 33.73 | 0.00653338 | COMPLETED |
| four_flush_weighted_24x24 / 3 | 13.349 | 12.948 | 34.44 | 0.00653338 | COMPLETED |

## Unresolved gates

No hosted timeout, address-space limit, concurrency, OAuth or ChatGPT turn acceptance was tested.
Convergence is reported, not used as a performance pass criterion.
