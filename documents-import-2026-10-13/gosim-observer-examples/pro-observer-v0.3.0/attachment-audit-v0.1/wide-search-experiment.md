# Wide search experiment on the attached observer

The wider search increased L1 total score from **6411.015273 to 6545.720770**, a gain of **134.705497 points (2.101157%)**, while charged CPU increased from **108.369 to 339.626 seconds**. The main observed gain came from better final contributions on targets reached by both policies, with a smaller net gain from changing which targets were reached. The 30% improvement target remains unmet.

This is a matched comparison of `attached-adaptive-py312/L1` and `attached-wide-py312/L1`: the same attachment, card, manifest policy settings, native arm64 Python 3.12.14, 900 normalized CPU budget, no-model mode and adaptive pacing. Wide changes only five existing settings: `V5_DEEP_ANCHORS=144`, `V5_DEEP_DENSE=160`, `V5_DEEP_POOL=4000`, `V5_REFINE_FIXED_T=0` and `V5_REFINE_ROUNDS=6`. Sources match the archive hashes and card files remained unchanged. The changes were tested jointly, so this experiment cannot isolate each setting's contribution.

| Official outcome | Adaptive control | Wide | Difference |
|---|---:|---:|---:|
| Total score | 6411.015273 | 6545.720770 | +134.705497 |
| Science sum | 6211.378363 | 6346.031699 | +134.653336 |
| Required targets missing | 2 | 2 | 0 |
| Request reward | 200 | 200 | 0 |
| Report settlement | 100 | 100 | 0 |
| Uniformity penalty | -0.363090 | -0.310929 | +0.052161 |
| Observe actions | 770 | 781 | +11 |
| Distinct observed targets | 7364 | 7395 | +31 |
| Process CPU seconds | 61.714 | 193.617 | +131.903 |
| Charged CPU seconds | 108.369 | 339.626 | +231.257 |
| Run wall seconds | 69.494 | 205.259 | +135.765 |

Wide used 37.74% of the 900-second charged budget and reached survey completion. Both logs report search level 0 throughout: 831 decisions for control and 843 for wide. Deep search is a separate boolean within level 0: control turned it on; wide turned it on, off and on again as pacing adjusted. Neither run recorded an exception fallback, a hard-cap event, a no-plan wait or a model application. There is no per-stage CPU trace for this attachment, so geometry, assignment, duration, refinement and bookkeeping costs cannot be separated. The available compute evidence is the official whole-run meter; it does not prove that all additional CPU was useful numerical search.

## Where the science gain appeared

Reconstructing each target's maximum valid contribution from six-decimal `observations.csv` scores gives the following decomposition. The raw reconstruction differs from official science by -0.000004 for control and +0.000019 for wide; official scores above remain authoritative.

| Final target contribution comparison | Targets | Approximate science difference |
|---|---:|---:|
| Reached by both policies | 7113 | +103.328678 |
| Reached only by wide | 282 | +169.899161 |
| Reached only by control | 251 | -138.574480 |
| Net change in target coverage | +31 | +31.324681 |

Among the common targets, 2722 improved, 2475 worsened and 1916 had unchanged best contribution. Approximately 76.74% of the science increase therefore came from the net contribution change on common targets. This is an outcome decomposition, not proof of a particular scheduling mechanism: field choice, exposure timing, duration and repeat selection changed together.

Chronological reconstruction of gains on first valid hits and later improvements gives **+50.519912** from first-hit contributions and **+84.133447** from winning repeat gains. Repeated exposure does not accumulate progress in this score; only an improvement over that target's previous best contribution adds science.

## Repeats and fiber use

| Valid-history metric | Adaptive control | Wide |
|---|---:|---:|
| Target hits | 9744 | 10197 |
| Repeated target hits | 2380 | 2802 |
| Repeats that increased best score | 2171 | 2344 |
| Repeats that did not increase best score | 209 | 458 |
| Nonwinning repeats as share of repeats | 8.78% | 16.35% |
| All zero-score target hits | 342 | 615 |
| Positive-score nonwinning target hits | 49 | 56 |
| Exposures with zero marginal science | 25 | 49 |
| Telescope seconds in zero-science exposures | 22200 | 21450 |
| Fiber seconds in nonwinning repeats | 267450 | 302400 |
| Mean targets assigned per exposure | 12.657 | 13.060 |
| Hits divided by assigned targets | 99.9795% | 99.9706% |

Wide increased repeat improvements, but it also added nonwinning repeats. Of the 249 additional nonwinning repeats, 242 were zero-score hits rather than positive contributions below a previous best. More zero-science exposures did **not** mean more telescope time with zero science: those exposures used 750 fewer seconds in total. A zero science increment is not automatically a useless action; required/request satisfaction, fault diagnosis and calibration are separate objectives. No claim about their per-action counterfactual value is available from these aggregate counts.

Both runs had excellent geometry hit rates. Mean realized hit factor decreased from 0.7141 to 0.6995, and mean evaluator quality decreased from 0.7104 to 0.6887. These are unweighted offline judge summaries, not quantities read from card truth by the live observer. They suggest that the score gain did not come from uniformly better observing quality, but do not isolate a cause.

## Duration distribution

The total observed time decreased from **847350 to 846600 seconds**. Mean duration decreased from 1100.455 to 1083.995 seconds; median remained 750 seconds, with 10th/90th percentiles 300/2400 seconds in both runs. Declared and realized duration distributions match in these runs; no clipping discrepancy appears in the recorded actions and decisions.

| Duration seconds | Adaptive exposures | Wide exposures |
|---|---:|---:|
| 150 | 5 | 7 |
| 300 | 204 | 224 |
| 450 | 77 | 50 |
| 600 | 39 | 55 |
| 750 | 63 | 55 |
| 900 | 93 | 95 |
| 1200 | 54 | 71 |
| 1500 | 52 | 47 |
| 1800 | 69 | 55 |
| 2400 | 53 | 68 |
| 3000 | 29 | 27 |
| 3600 | 32 | 27 |

Science per observed telescope hour increased from 26.3893 to 26.9853. The wider search changed the mix of durations and increased average fiber occupancy, while the total available observing time and science scoring rules stayed fixed.

The next implementation should preserve the demonstrated common-target contribution improvements and measure why zero-score repeats grew. Broader search alone has demonstrated a modest L1 gain; it has not established the requested 30% improvement or performance on L2, L3, L4 or the separately supplied 300-CPU public-test scenario.

The numeric reconstruction is saved in [wide-search-experiment.json](/Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/attachment-audit-v0.1/wide-search-experiment.json), with compact rows in [wide-search-experiment.csv](/Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/attachment-audit-v0.1/wide-search-experiment.csv). Official matched results remain in [matched-native312.csv](/Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/pro-evaluation-v0.2.0/matched-native312.csv).
