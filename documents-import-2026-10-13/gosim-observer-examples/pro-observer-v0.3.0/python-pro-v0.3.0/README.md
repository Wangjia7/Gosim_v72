# Pro observer v0.3.0 RC5 — experimental delivery checkpoint

RC5 preserves the uploaded observer's season planning, fault diagnosis, duty-log and optional advisory modules, with bounded geometry, timing, state, exposure-search and CPU corrections. **The requested 30% score improvement has not been achieved.** The selected policy has 103 passing native Python 3.12 tests; tests establish covered behaviors, not score gains.

Completed selected-policy totals are L1 6587.434006–6594.574242 across two measurements (+5.63–5.74% versus original Pro), L2 6949.603865 (+11.22%), and prospective heldout L3 7197.284324 (+11.06%). All exceed the matching attachment reference. L3 used settings frozen before evaluation and was not used for tuning. Prospective heldout L4 completed at 7299.303567 (+9.376% versus original). Full score components, CPU, failed/negative trials and limitations are in [the evaluation report](../pro-evaluation-v0.3.0/REPORT.md); historical implementation details are in [CHANGELOG.md](CHANGELOG.md).

## Running and reproducing

Use native Python 3.12 and the standard library; no new runtime packages are required. The entrypoint reads JSONL protocol v4 from stdin:

```sh
OBSERVER_MODEL_DISABLED=1 python3.12 -B agent.py
python3.12 -B -m unittest discover -s tests -v
```

Running without protocol input does not start a survey. Direct Python execution reads environment variables and source defaults; **it does not load `observer.project.json`**. The platform or benchmark harness loads the manifest. Exact frozen-policy reproduction, including every environment override, is in [benchmarks/README.md](benchmarks/README.md) and [checkpoint-freeze.json](../pro-evaluation-v0.3.0/checkpoint-freeze.json).

**Delivery configuration is applied:** the manifest environment equals the frozen `policy_settings`, including `OBSERVER_MODEL_DISABLED=1` for operation without an external service. The 18 frozen Python runtime hashes are unchanged. Direct source execution still requires the explicit reproduction environment; it does not load the manifest.

## Selected settings and source fallbacks

Existing `_env` settings prefer `V5_*` over their `PRO_*` alias. New stage flags use `PRO_*` directly. The table distinguishes direct-execution fallbacks from the applied frozen delivery environment.

| Setting | Source fallback | Delivery manifest / unchanged fallback |
|---|---:|---:|
| `OBSERVER_MODEL_DISABLED` | environment-dependent | 1 |
| `V5_FIXED_LEVEL` | -1 | -1 (adaptive) |
| `PRO_EVENT_DURATIONS` | 0 | 0 |
| `PRO_EXACT_TIME_PRICE` | 0 | 0 |
| `PRO_LEADER_REFINE` | 0 | 1 |
| `PRO_WIDTH_AWARE_GATE` | 0 | 0 |
| `PRO_SEARCH_WIDTH_MAX` | 5 | 20 |
| `PRO_SCIENCE_ANCHORS` | 32 | 64 |
| `V5_DEEP_ANCHORS` / `V5_DEEP_DENSE` / `V5_DEEP_POOL` | 24 / 40 / 1000 | 48 / 80 / 2000 |
| lambda fraction / kappa | .45 / 1 | .45 / 1 |
| `PRO_CPU_RESERVE_NORMALIZED` | 20 | 20 via unchanged source default |
| `PRO_GAIN_CACHE` / `PRO_SCORE_COLUMNS` | 1 / 1 | 1 / 1 via unchanged source defaults |

The complete nonsecret environment, rather than this abbreviated table, is the reproduction authority. CPU reserve is 20 normalized seconds, separate from the retained wall-time reserve. Absolute CPU/wall deadlines protect final responses; unused CPU alone does not establish a policy defect.

## Behavior and diagnostics

Actual-center queries cover the loaded fiber footprint, shifted centers are requeried, and final commands are checked against exact cells. Declared durations and clipped actual intervals remain distinct; timed requests require the whole interval to fit. Required-state evidence is replayed after corrections without equating best science score with hidden raw factor. Season planning uses replacement exposure cost and marginal score; joint program/duration search retains legal best-so-far actions.

`PRO_LOG_PATH` selects the structured JSONL sidecar (default `decision-log.jsonl`). It records source/config/state identities, actions, predicted contributions, outcome transitions, constraints and component CPU. Unavailable authoritative per-step values remain unknown. Internal failures record only exception class and up to eight traceback locations; explicit `INTERNAL_ERROR` records alarm in offline review. Protocol stdout remains clean.

[QA.md](QA.md) documents whole-run review, individual step diagnostics, replay, bounded context and optional remote review. Missing credentials or model-disabled operation works without a service. Optional review cannot change state, score or actions. No external model requests were made in this validation.

## Evidence, packaging and limits

[PROVENANCE.md](PROVENANCE.md) identifies the source archive, original baseline, runtime, rules and preservation checks. `evidence/` contains approved plans, normalized patches, source hashes, historical source snapshots and [baseline diagnostic profiles](evidence/baseline-profile/README.md). Original Pro and the attachment remain separate and unchanged. No Git history accompanies the exports.

The packaging tool excludes credentials, tests, benchmarks, logs and evidence from the submission ZIP:

```sh
python3.12 pack_agent.py --out ../python-pro-v0.3.0.zip
```

Retain this full directory for reproducibility. Local native execution does not certify the untested pinned/hosted container or platform score. The attachment's negative public-test report cannot be exactly reproduced because its card/source linkage is missing. The proposed v0.4 substantive policy plan remains unapproved and unimplemented. No remote submission or push has occurred.

Final native validation: 103 tests passed under source defaults (0.373 seconds) and the delivery manifest environment (0.886 seconds); [test evidence](evidence/final-tests.json). Four-card aggregate total gain is +9.367% versus original and +2.626% versus attachment; every card fails the 30% criterion. See [frozen validation](../pro-evaluation-v0.3.0/frozen-validation.md). The [submission ZIP](../python-pro-v0.3.0.zip) passes native entrypoint, frozen-hash and packaging checks; see [package validation](evidence/package-validation.json). The [delivery receipt](../pro-evaluation-v0.3.0/delivery-receipt.json) records installation status, destination and copied-file hashes for `gosim-observer-examples/pro-observer-v0.3.0`. No hosted-container validation or remote upload is claimed.
