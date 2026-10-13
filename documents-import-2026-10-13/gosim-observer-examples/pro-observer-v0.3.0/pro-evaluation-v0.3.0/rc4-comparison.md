Both RC4 L1 runs completed the full survey without internal errors, hard CPU caps, or source/card mutation. Frozen RC4 had 102 passing tests reported by the implementation owner before execution. The failed RC3 archive remains preserved.

| Policy | Total | Science | Required missing | Request reward | Charged CPU / 900 | Process CPU | Actual width median / max |
|---|---:|---:|---:|---:|---:|---:|---:|
| rc4-dense-fix | 6587.434006 | 6387.917565 | 2 | 200 | 870.546 | 474.465 | 4.540 / 20 |
| rc4-width-gate | 6592.094057 | 6392.534293 | 2 | 200 | 873.807 | 488.964 | 3.900 / 20 |

Gate=1 improves total by 4.660051 (+0.070742%) and science by 4.616728 over the gate=0 control. This small single-card difference does not establish the requested 30% improvement. Width greater than 1 proves deep search active: 511/832 decisions (61.42%) in control versus 767/826 (92.86%) with the gate. Exact deep enabled duty is unavailable because width 1 can also be deep and the flag is not logged. Gate levels were 0:795, 1:19, 4:12 versus control 0:826, 1:6. All stage CPU sums and limitations are retained in each stage-analysis.json. No L2 or heldout run was launched.
