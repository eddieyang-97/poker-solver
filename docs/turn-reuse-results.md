# Local turn reuse experiment

Predeclared synthetic targets, no fitted parameters. Source family and card mapping supplied; not nearest-neighbour search or organic demand. Exact/equivalent targets excluded from approximation summaries.

Unlimited local in-process wall/CPU (imports excluded). Reference training isolated. Not hosted/Linux budget acceptance.

| Target | Classification | Error: scaled / adjusted / evaluated (% pot) | BR width (% pot) | Bound | Online wall |
| --- | --- | ---: | ---: | --- | ---: |
| exact_repeat | equivalent_and_verified | 0.0001 / 0.0001 / 0.0001 | 0.0053 | bounded_root_value | 0.0166s |
| global_suits | equivalent_and_verified | 0.0001 / 0.0001 / 0.0001 | 0.0053 | bounded_root_value | 0.0296s |
| double_money | equivalent_and_verified | 0.0001 / 0.0001 / 0.0001 | 0.0053 | bounded_root_value | 0.0230s |
| suits_and_money | equivalent_and_verified | 0.0000 / 0.0000 / 0.0000 | 0.0005 | bounded_root_value | 0.0297s |
| dry_bluff_weight_0.1 | target_fixed_policy_evaluation | 1.3668 / 29.2603 / 52.4100 | 52.7111 | abstain_wide_bound | 0.0157s |
| dry_bluff_weight_0.9 | target_fixed_policy_evaluation | 10.3823 / 4.4718 / 0.0043 | 9.6548 | abstain_wide_bound | 0.0208s |
| dry_stack_160 | target_fixed_policy_evaluation | 0.0001 / 0.0001 / 0.0001 | 0.0053 | bounded_root_value | 0.0178s |
| dry_turn_075 | target_fixed_policy_evaluation | 1.3668 / 1.3668 / 6.8483 | 14.8257 | abstain_wide_bound | 0.0187s |
| dry_river_pot | target_fixed_policy_evaluation | 1.3668 / 1.3668 / 6.5519 | 11.8821 | abstain_wide_bound | 0.0155s |
| dry_turn_9s | target_fixed_policy_evaluation | 0.0001 / 0.0001 / 0.0001 | 0.0053 | bounded_root_value | 0.0205s |
| dry_turn_Qs | target_fixed_policy_evaluation | 1.3668 / 3.3124 / 5.7546 | 8.3114 | abstain_wide_bound | 0.0236s |
| dry_turn_Js | target_fixed_policy_evaluation | 1.3668 / 3.3124 / 5.7546 | 8.3114 | abstain_wide_bound | 0.0195s |
| collision_weight_07 | target_fixed_policy_evaluation | 13.5358 / 8.6218 / 0.0000 | 1.6590 | abstain_wide_bound | 0.0179s |
| collision_turn_9s | target_fixed_policy_evaluation | 0.0000 / 0.0000 / 0.0000 | 0.0005 | bounded_root_value | 0.0206s |
| flush_loses_suit | target_fixed_policy_evaluation | 21.3282 / 9.6542 / 16.3513 | 54.6777 | abstain_wide_bound | 0.0431s |
| flush_ace_weight_0.1 | target_fixed_policy_evaluation | 21.4960 / 9.2046 / 0.3469 | 6.2532 | abstain_wide_bound | 0.0270s |
| flush_ace_weight_1 | target_fixed_policy_evaluation | 16.1505 / 5.2273 / 2.6444 | 5.4822 | abstain_wide_bound | 0.0283s |
| new_hand | unsupported: Unmapped range support | — | — | — | — |
| extra_size | unsupported: Incompatible actor/street/action order | — | — | — | — |
| changed_allin_topology | unsupported: Incompatible tree topology | — | — | — | — |

## Summary

```json
{
  "targets": 20,
  "strict_hits": 1,
  "equivalent_hits": 4,
  "unsupported": 3,
  "changed_input_targets": 13,
  "mapped_strategic_duplicates": 3,
  "approximate_targets": 10,
  "narrow_changed_input_bounds": 3,
  "narrow_transfer_bounds": 0,
  "narrow_short_solve_bounds": 10,
  "compressed_catalog_bytes": 47235,
  "errors": {
    "scaled_cached_ev": {
      "median_pct_pot": 5.87457001066311,
      "max_pct_pot": 21.496020461432963
    },
    "equity_adjusted_ev": {
      "median_pct_pot": 4.849562320610778,
      "max_pct_pot": 29.260305878144006
    },
    "target_fixed_policy_ev": {
      "median_pct_pot": 5.754630735676898,
      "max_pct_pot": 52.41001179957795
    },
    "bound_midpoint": {
      "median_pct_pot": 2.7939391832378746,
      "max_pct_pot": 26.055025215109318
    },
    "short_fresh_ev": {
      "median_pct_pot": 0.011846067291571671,
      "max_pct_pot": 0.02511725822757427
    }
  },
  "approximation_speedups": {
    "median_fresh2000_over_lookup_transfer_br": 105.01260355077333,
    "median_fresh2000_over_fresh200": 9.497968072764095
  }
}
```

## Integrity failures

None. Approximation errors and wide-bound abstentions are measured outcomes, not passing solutions.
