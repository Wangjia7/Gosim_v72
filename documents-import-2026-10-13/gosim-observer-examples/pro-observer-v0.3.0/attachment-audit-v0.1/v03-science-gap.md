# L1 science-gap diagnosis

Completed public-run artifacts only. Primary run: `candidate-no-events-adaptive/L1` (the retrospectively named RC1 without duration events). Secondary: `rc2-budget12-refine/L1`. No judge execution, hidden scenario files, or runtime edits.

| Diagnostic | RC1 | RC2 refinement |
|---|---:|---:|
| Official science | 6352.219 | 6373.934 |
| Observe actions / observed targets | 808 / 7434 | 787 / 7385 |
| Telescope observing hours | 234.583 | 234.667 |
| Occupied fiber-hours | 3139.850 | 3167.242 |
| Unused fiber-hours during observes | 613.317 | 587.092 |
| Time-weighted fiber fill | 83.65% | 84.35% |
| Strictly below final best-score fiber-hours | 422.167 | 401.583 |
| Final nonrepresentative fiber-hours, including tied duplicates | 425.542 | 405.000 |
| Already nonwinning when observed, fiber-hours | 88.750 | 86.375 |
| Saturation excess, fiber-hours | 549.897 | 586.885 |
| Overlap: final nonrepresentative and saturation excess | 2.336 | 4.873 |

Final nonrepresentative exposures account for **13.55% of occupied fiber-time in RC1**, versus only 2.83% already nonwinning at execution. Thus about **336.792 fiber-hours** first added science and were subsequently replaced or made redundant. The earlier immediate-repeat diagnostic misses most of that retrospective replacement. Strict final losers exclude rounded-score ties; one earliest maximum-score observation represents each target for the inclusive diagnostic.

Saturation excess is **17.51% of RC1 occupied fiber-time**. It uses the official recorded quality and public target flux: raw factor = flux × actual duration × recorded quality / 450; excess = duration × max(0, 1 − 1/raw factor). Reconstructed clipped factors agree with CSV factors within 0.0000021, consistent with CSV rounding. This is a fixed-realized-quality accounting estimate: it does not establish that an earlier ending would have precisely the same quality or program multiplier.

The union of final nonrepresentative time and saturation excess is **973.102 fiber-hours**, or **30.99% of occupied fiber-time**. These quantities must not be added without removing their overlap. Nor can fiber-hours be treated as freely recoverable telescope hours: co-observed targets share exposure duration, and unused cells may lack reachable unfinished targets. RC2 illustrates the tradeoff: it removes 20.542 nonrepresentative fiber-hours and fills 26.225 additional fiber-hours, but adds 36.988 saturation-excess fiber-hours; official science rises only 21.716 (0.34%).

The approximate required science level of 7807.544 is still **1455.325 above RC1**, a **22.91% science increase**. Root's paired immediate prediction comparison (6512.96 predicted versus 6346.68 actual across 807 observes) indicates roughly 2.6% optimism; its sample omits one action, so it should not be equated directly with the full official science above. Immediate quality bias alone is too small to explain this gap.

A bounded next hypothesis is to compare mild completion shaping (`PRO_KAPPA=1.3` or `1.5`) against 1.0, keeping other settings fixed, and separately a lower time-price share (`PRO_LAMBDA_FRAC=.30` versus `.45`). Completion shaping could favor fewer eventual partial replacements; a lower time price could lengthen exposures and trade replacement against saturation. Neither is presumed beneficial: earlier KAPPA=2 regressed, and RC2 already shows how less replacement can coincide with more saturation. Retain only configurations that improve official score under matched CPU limits; compare the replacement/saturation/fill diagnostics alongside score. This evidence supports these targeted tests, not a claim that they will reach 30%.

Analysis script: `work/science-gap/analyze.py`; intermediate results: `work/science-gap/results.jsonl`. Inputs: completed run `observations.csv`, `decisions.csv`, `score_report.json`, and L1 public `targets.csv` plus scoring constants. Analysis elapsed approximately 0.035 seconds.
