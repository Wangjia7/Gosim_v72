# Matched local evaluation checkpoint

Native arm64 Python 3.12.14, unchanged local engine, no external model, 900 normalized CPU seconds per episode. Original and attached fixed-tier references are explicit; adaptive controls are separately identified. Full source/config hashes, all components and raw artifacts are linked through results.json. Local results do not establish hidden platform performance.

| Card | Configuration | Completion | Total | Science | vs original | Charged CPU | 30% met |
|---|---|---|---:|---:|---:|---:|---|
| L1 | attached-9c656-py312 | complete | 6411.015 | 6211.378 | +2.797% | 105.973 | no |
| L1 | attached-adaptive-py312 | complete | 6411.015 | 6211.378 | +2.797% | 108.369 | no |
| L1 | attached-wide-py312 | complete | 6545.721 | 6346.032 | +4.957% | 339.626 | no |
| L1 | candidate-all-adaptive | complete | 6437.544 | 6238.276 | +3.222% | 576.705 | no |
| L1 | candidate-no-events-adaptive | complete | 6551.839 | 6352.219 | +5.055% | 561.847 | no |
| L1 | original-pro-py312 | complete | 6236.572 | 6037.342 | +0.000% | 157.256 | no |
| L1 | rc2-budget12-control | complete | 6514.402 | 6314.794 | +4.455% | 527.269 | no |
| L1 | rc2-budget12-refine | complete | 6573.447 | 6373.934 | +5.402% | 510.477 | no |
| L1 | rc2-fullbudget-exact-price | complete | 6571.169 | 6371.661 | +5.365% | 619.060 | no |
| L1 | rc2-fullbudget-refine | complete | 6600.591 | 6401.039 | +5.837% | 652.323 | no |
| L1 | rc3-fullbudget-refine | FAILED/INCOMPLETE | 6187.724 | 6088.401 | not comparable | 725.307 | not comparable |
| L1 | rc4-dense-fix | complete | 6587.434 | 6387.918 | +5.626% | 870.546 | no |
| L1 | rc4-width-gate | complete | 6592.094 | 6392.534 | +5.701% | 873.807 | no |
| L1 | rc5-kappa130 | complete | 6585.837 | 6386.248 | +5.600% | 872.716 | no |
| L1 | rc5-lambda060 | complete | 6551.687 | 6351.944 | +5.053% | 874.393 | no |
| L1 | rc5-validation | complete | 6594.574 | 6395.058 | +5.740% | 861.617 | no |
| L1 | successor-py312 | complete | 6362.586 | 6162.853 | +2.021% | 409.575 | no |
| L2 | attached-9c656-py312 | complete | 6715.434 | 6567.188 | +7.475% | 117.219 | no |
| L2 | candidate-no-events-adaptive | complete | 6746.161 | 6597.449 | +7.967% | 666.478 | no |
| L2 | original-pro-py312 | complete | 6248.344 | 6202.895 | +0.000% | 162.855 | no |
| L2 | rc5-validation | complete | 6949.604 | 6801.889 | +11.223% | 867.781 | no |
| L2 | successor-py312 | complete | 6536.477 | 6390.077 | +4.611% | 431.112 | no |
| L3 | attached-9c656-py312 | complete | 7033.334 | 6783.745 | +8.529% | 133.958 | no |
| L3 | original-pro-py312 | complete | 6480.589 | 6231.273 | +0.000% | 297.309 | no |
| L3 | rc5-validation | complete | 7197.284 | 6947.448 | +11.059% | 874.450 | no |
| L4 | attached-9c656-py312 | complete | 7163.536 | 6914.368 | +7.342% | 133.765 | no |
| L4 | original-pro-py312 | complete | 6673.585 | 6475.596 | +0.000% | 314.439 | no |
| L4 | rc5-validation | complete | 7299.304 | 7050.496 | +9.376% | 872.816 | no |

CPU is normalized charge, not process CPU or wall time. Complete component tables are in results.csv. Failed/incomplete rows retain their partial settlement for audit and are not full-survey performance comparisons. Missing or incomplete native original/attachment references produce null comparisons and no acceptance pass. A nonpositive original total has no percentage-improvement threshold; it cannot produce a 30% acceptance pass. A passed test suite or a higher proxy utility is not a demonstrated score gain.

The supplied negative v4-public-test report uses a different card, 300 CPU budget and model-enabled policy; it is excluded from this comparison. Its exact card/source linkage is unresolved.
