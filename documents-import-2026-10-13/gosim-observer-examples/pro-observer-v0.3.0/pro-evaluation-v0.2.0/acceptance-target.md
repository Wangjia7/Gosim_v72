# Updated acceptance target

The user added a minimum 30% total-score improvement over the original Pro during implementation. We apply this conservatively to each evaluated scenario, using identical inputs, no-model settings and a 900 normalized CPU-second budget. A gain in the sum across cards does not substitute for a per-card pass. Correctness and budget compliance remain necessary.

Development baseline fixed-level scores:

| Card | Original Pro | Required total (×1.30) |
|---|---:|---:|
| L1 | 6236.572199 | 8107.543859 |
| L2 | 6248.343772 | 8122.846904 |

The first corrected program-aware candidate scores 6274.390580 and 6439.756392. It **does not pass** this target. The implementation is not promoted as a 30% improvement.

Diagnostics point to incomplete exposures and repeated work as the main remaining loss. L1 public weights sum to 7098; even assigning the maximum 1.2 program multiplier to every saturated target gives a science ceiling of 8517.6. This is an optimistic ceiling, not a feasible schedule. The 30% target would need at least 7807.54 science if all required penalties vanished and the currently observed 300 positive bonus points were retained. Programs, two remaining required misses and sub-point uniformity penalty alone cannot close the gap.

We are testing completion shaping, reduced telescope-time price and a separate science-only time-price estimate within the existing planner. Failed variants are retained. L3/L4 remain held out from tuning. No runtime access to hidden card inputs or real model API calls is introduced.
