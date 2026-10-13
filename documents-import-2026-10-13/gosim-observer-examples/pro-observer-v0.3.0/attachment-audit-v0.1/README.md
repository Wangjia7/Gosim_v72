# Attached observer analysis v0.1

The attached source is the stronger measured starting point. Under the same native Python 3.12, unchanged official local engine, identical L1/L2 cards, disabled external model and 900 normalized CPU budget, it beats both original Pro and our v0.2.0 candidate.

| Card | Original Pro | v0.2.0 | Attached source | Attachment vs original | Attachment science | Attachment charged CPU |
|---|---:|---:|---:|---:|---:|---:|
| L1 | 6236.572199 | 6362.586103 | 6411.015273 | +2.7971% | 6211.378363 | 105.973 |
| L2 | 6248.343772 | 6536.476794 | 6715.434225 | +7.4754% | 6567.187870 | 117.219 |

All six runs completed normally with source/input hashes preserved. They use level 0 for deterministic comparison; the attachment also uses its default deep-search mode. An additional attachment adaptive L1 control produced the identical 831-action sequence and score, using 108.369 normalized CPU seconds. Subsequent successor experiments are reported separately below.

The 30% requirement has **not** been achieved. The new version must also beat this stronger attachment under matching conditions; comparing its negative public-test report against a positive L1 result would be invalid.

The supplied public-test result is -121.937111: science 974.785212, required penalty -1050 for 21 misses, uniformity -46.722322. The survey completed after 15.393 of its 300 charged CPU seconds; it did not exhaust the budget. Its scenario card and exact link to the supplied source are missing, and model advice was enabled. These differences prevent a matched reproduction from these archives alone.

## Findings and next version

The attachment retains useful season planning, geometry caches and fault handling. Eight synthetic reproductions identify incorrect broad geometry coverage, score/raw-factor conflation, hard-coded required threshold, omitted short windows, request intervals, replacement-cost modeling and correction-triggered repricing. The probes show correctness mismatches, not the size or sign of whole-run score changes.

The user approved the [v0.3.0 plan](implementation-plan.md) on 2026-10-07. It preserves the attachment's modules and applies incremental corrections, budget-bounded joint search, structured logging and isolated optional QA. Original source and archives remain unchanged.

- [Exact regression evidence](regression-probes.md)
- [Probe values and hashes](probe-results.json)
- [Archive provenance](archive-provenance.json)
- [Complete matched score/CPU table](matched-native312.csv)
- [Runtime identity](runtime-evidence.json)
- [New rules evidence and unresolved differences](rules-evidence-addendum.md)

Raw run records and credential-free execution snapshots are retained under `../pro-evaluation-v0.2.0/{original-pro-py312,successor-py312,attached-9c656-py312}/{L1,L2}`. Native source execution is not an exact reproduction of the attachment's pinned container image. No external model request, remote submission, or push was performed by this work.

## v0.3 checkpoint results

The rc1 no-event successor completed L1/L2 with totals 6551.839453 / 6746.161380: summed +1.31% over the attachment and +6.51% over original Pro. This is a paired checkpoint, not the latest source result. The best completed rc2 L1 experiment, `rc2-fullbudget-refine`, reaches 6600.590852 (science 6401.038511) at 652.323 normalized CPU seconds: +2.96% over the attachment and +5.84% over original Pro. It has no completed paired L2 result. Both remain below the requested 30%; L1 needs 8107.543859 total. The completed rc2 exact-time-price run scored 6571.168789 at 619.060 normalized CPU seconds; it did not improve the rc2 best. The rc3 run failed and is INCOMPLETE; corrected rc4 source is under evaluation.

See [the current evaluation collection](../pro-evaluation-v0.3.0/results.json), [the science-gap diagnosis](v03-science-gap.md), and [reproduction settings](../python-pro-v0.3.0/benchmarks/README.md). The proposed v0.4 policy plan awaits user approval; no v0.4 implementation is part of these results.

**Search-width caveat:** rc2 labels/settings requesting width 12 or 20 do not represent that actual breadth: the historical rc2 planner capped its applied multiplier at 5, while the agent logs the requested value and normalizes its cost estimate by that value. The completed scores remain valid measurements of that frozen implementation. The full-budget run's larger base limits (48 anchors / 80 dense seeds / 2000 pool entries) still broaden search relative to 24/40/1000. The rc3 run failed with a density-bin KeyError and is INCOMPLETE, never a valid full-survey score. Current rc4 fixes that defect and passed 102 integrated tests; its benchmark remains in progress. Historical reproduction uses the preserved pre-width-fix ZIP.
