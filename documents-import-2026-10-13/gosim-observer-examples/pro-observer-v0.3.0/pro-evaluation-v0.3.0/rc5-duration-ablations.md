All three L1 policies completed the full survey with two required targets missing and both timed requests completed. The RC5 implementation owner reported 103 passing tests before execution; observer scheduling policy was unchanged from RC4. Each ablation changes only the indicated parameter against RC4 width gate.

| Policy | Total | Delta vs control | Science | Observes | Mean duration | Charged CPU / 900 |
|---|---:|---:|---:|---:|---:|---:|
| rc4-width-gate | 6592.094057 | +0.000000 | 6392.534293 | 765 | 1102.980 s | 873.807 |
| rc5-lambda060 | 6551.687157 | -40.406900 | 6351.944205 | 839 | 1006.985 s | 874.393 |
| rc5-kappa130 | 6585.836507 | -6.257550 | 6386.247801 | 692 | 1221.893 s | 872.716 |

PRO_LAMBDA_FRAC=0.60 retains KAPPA=1; PRO_KAPPA=1.3 retains LAMBDA_FRAC=0.45. Both variants retain width gate=1, width max20, leader refine=1, deep anchors48/dense80/pool2000, science anchors64, event durations=0 and exact time price=0. Both ablations reduced L1 science and total score. These results do not support a 30% improvement claim. All source snapshot and card hashes remained unchanged, with no internal error or hard CPU cap. Exact deep enabled duty remains unlogged; width greater than1 is only a lower bound. Stage-analysis.json contains component process CPU and width details. Judges are idle; no L2 or heldout run was launched.
