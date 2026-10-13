The frozen RC5 checkpoint completed L3 and L4, and both unchanged references completed each card. No internal errors, hard CPU caps, or source/card mutations occurred. All candidate snapshots match the 18 Python-file hashes recorded prospectively in checkpoint-freeze.json. Policy settings were held constant; no tuning followed heldout outcomes. All judges are idle.

| Card | Split | Original total | Attachment total | Candidate total | Total gain vs original | Total gain vs attachment | Science gain vs original | Science gain vs attachment |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| L1 | development | 6236.572199 | 6411.015273 | 6594.574242 | +5.740% | +2.863% | +5.925% | +2.957% |
| L2 | development | 6248.343772 | 6715.434225 | 6949.603865 | +11.223% | +3.487% | +9.657% | +3.574% |
| L3 | heldout | 6480.589228 | 7033.333558 | 7197.284324 | +11.059% | +2.331% | +11.493% | +2.413% |
| L4 | heldout | 6673.584941 | 7163.536276 | 7299.303567 | +9.376% | +1.895% | +8.878% | +1.969% |

The candidate beats the attachment on every card but fails the requested 30% total-score improvement over original Pro on every card. Science gain is reported separately because settlement, required penalties, request rewards and uniformity also affect total score.

heldout: aggregate total gain +10.205% versus original Pro and +2.111% versus attachment. These sums do not replace per-card acceptance.

all_four: aggregate total gain +9.367% versus original Pro and +2.626% versus attachment. These sums do not replace per-card acceptance.

| Heldout policy | Card | Science | Required missing | Requests | Process CPU | Charged CPU /900 |
|---|---|---:|---:|---:|---:|---:|
| original-pro-py312 | L3 | 6231.272529 | 1 | 200 | 165.276 | 297.309 |
| attached-9c656-py312 | L3 | 6783.745199 | 1 | 200 | 72.279 | 133.958 |
| rc5-validation | L3 | 6947.447907 | 1 | 200 | 482.305 | 874.450 |
| original-pro-py312 | L4 | 6475.595608 | 2 | 200 | 171.818 | 314.439 |
| attached-9c656-py312 | L4 | 6914.367930 | 1 | 200 | 73.302 | 133.765 |
| rc5-validation | L4 | 7050.496291 | 1 | 200 | 492.881 | 872.816 |

Each run retains exact commands, nonsecret settings, source/calibration/card hashes, raw actions and official full score components. Candidate stage-analysis.json files summarize logged stage process CPU and actual widths; width greater than1 proves deep search active but exact enabled duty is not logged. Logged stage counters are diagnostic measurements, not independently metered additive CPU partitions. Original and attachment lack equivalent stage instrumentation.

The L1 same-policy repeat differed from RC4 by +7.140236 and first diverged at action74, illustrating adaptive timing/calibration sensitivity; no repeat-derived confidence interval is claimed. RC3 early KeyError and Python3.9 attachment startup failures are preserved in frozen-validation.json as failure references, excluded from completed matched performance comparisons. The supplied remote public-test300 result uses another unprovided scenario and remains incomparable. All runs disable model calls.
