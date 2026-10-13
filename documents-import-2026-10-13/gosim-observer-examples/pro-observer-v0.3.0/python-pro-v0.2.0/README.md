# Pro observer v0.2.0

Versioned successor to the exported `python-pro` Survey26 observer. The original Python, Rust and TypeScript Pro directories are preserved. This version retains the standard-library agent/planner/advisor layout and `participant-agent-protocol-v4` JSONL interface. It is an implementation candidate: paired benchmarks and final feature defaults are still being evaluated. No hidden-card performance improvement is claimed.

The supplied survey-observing skills guide geometry, assignment, scheduling, exposure, state, CPU and retrospective changes. Current competition definitions and provenance are recorded in [rules-snapshot.md](rules-snapshot.md) and [PROVENANCE.md](PROVENANCE.md). See [CHANGELOG.md](CHANGELOG.md), [QA.md](QA.md) and [benchmarks/README.md](benchmarks/README.md).

## Run and validate

The platform manifest uses `python:3.12-slim` and runs `python3 -u agent.py`. JSONL protocol messages enter stdin; only official response objects leave stdout. Human-readable diagnostics use stderr, structured records use a sidecar. Local native macOS validation uses Python 3.9.6; the actual platform Python 3.12/container execution remains unverified until separately run.

From this folder, with the supplied evaluator at its original location:

```sh
OBSERVER_MODEL_DISABLED=1 PRO_LOG_PATH=/tmp/pro-v020-decisions.jsonl python3 /Users/jqwang/Documents/gosim-observer-examples/runner/run_local.py --inherit-env --card /Users/jqwang/Documents/gosim-observer-examples/local-cards/L1 --agent "python3 -B agent.py" --agent-cwd . --wallclock 900 --out /tmp/pro-v020-L1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 pack_agent.py --out /tmp/python-pro-v0.2.0.zip
```

For comparisons use the isolated benchmark harness, which excludes credentials and source `.env`, snapshots source and records commands/hashes:

```sh
PYTHONDONTWRITEBYTECODE=1 /Library/Developer/CommandLineTools/usr/bin/python3 benchmarks/run.py --agent-dir . --card L1 --label successor-fixed0
PYTHONDONTWRITEBYTECODE=1 /Library/Developer/CommandLineTools/usr/bin/python3 benchmarks/run.py --agent-dir . --card L1 --label successor-adaptive --adaptive
```

The observer reads public protocol state and its own outcomes. It never opens task-card files at runtime. The evaluator reads cards. Do not run real provider calls, upload a package or start remote evaluations without the applicable authorization.

## Models are optional

`OBSERVER_MODEL_DISABLED=1` explicitly selects rules only. Missing `OPENAI_API_KEY`/`KIMI_API_KEY` now also selects rules only instead of aborting startup. When configured, the existing advisor starts night-plan and fault-review calls at night boundaries and may request paid-fault-report confirmation. These advisory stages preserve their existing role; they are distinct from retrospective QA. `OPENAI_BASE_URL` and `OPENAI_MODEL` configure that client; inherited defaults remain the Kimi-compatible endpoint and `k3`. No model is required to observe.

Optional retrospective review runs outside the observer. It reads logs and can diagnose/propose ablations; it cannot mutate authoritative state, score, geometry or deadlines:

```sh
python3 qa_review.py run decision-log.jsonl
python3 qa_review.py step decision-log.jsonl --step 12
python3 qa_review.py replay decision-log.jsonl > reviews.jsonl
```

Remote QA requires explicit `--remote` plus `PRO_REVIEW_BASE_URL`, `PRO_REVIEW_MODEL`, `PRO_REVIEW_API_KEY`; no default provider or automatic credential inheritance. It has total timeout, retry/size/in-flight limits and validated responses. Offline reviews work without any service. Every action is logged and a subsequent outcome is correlated; unfinished feedback stays pending. Whole-log review retains the latest 1000 records; streaming replay covers all steps. See [QA.md](QA.md).

## Configuration and ablations

Existing `PRO_*` tunables retain their names. Numeric feature flags accept 0 or 1; settings are read at startup. Current source defaults below are provisional until paired evaluation is complete.

| Variable | Current default | Purpose |
|---|---:|---|
| `PRO_GEOMETRY` |1| Loaded fiber footprint, exact center queries and configurable central fibers |
| `PRO_STATE_EVIDENCE` |1| Replayable hit evidence and required-factor certainty bounds |
| `PRO_TEMPORAL` |1| Full request-interval credit and remaining-window ranking |
| `PRO_PROGRAM_AWARE` |1| Leading-candidate assignment/duration/declared-program evaluation |
| `PRO_EVENT_DURATIONS` |1| Bounded event breakpoint refinement |
| `PRO_GAIN_CACHE` |1| Per-decision gain cache |
| `PRO_SCIENCE_ANCHORS` |0 (experimental)| Extra seeds based on marginal science, before proxy-pool truncation |
| `PRO_SCIENCE_TIME_PRICE` |0| Experimental science-only time price; tested variants did not improve acceptance |
| `PRO_EXACT_TOPK` |6| Leading centers refined exactly |
| `PRO_EVENT_MAX`, `PRO_EVENT_LIMIT` |24,24| Bounded breakpoint construction/evaluation |
| `PRO_SPECIAL_ANCHORS` |3| Additional required/request anchor quota |
| `PRO_CPU_RESERVE` |2.0| Process CPU seconds reserved before further work |
| `PRO_FIXED_LEVEL` |-1| Adaptive pacing;0 pins full search for policy comparisons |
| `PRO_LOG_PATH` |`decision-log.jsonl`| Append-only sidecar; write failure falls back to stderr |

Flags isolate optimization stages, but switching them all off is not identical to the original: mandatory action validity, budget guards and logging remain. Use the preserved baseline directory for exact baseline comparisons. Roll back by selecting that directory or a documented feature ablation. Do not overwrite original sources.

## Rules and uncertainty

Science is the maximum valid per-target contribution, never cumulative exposure progress. Required/uniformity satisfaction depends on maximum raw factor; program bonuses cannot substitute. Requests count exposures wholly inside their windows, and award only completed-request reward. Loaded card values override illustrative constants.

Feedback hides raw quality, raw factor and actual per-target band. Required status is confirmed/unsatisfied/unknown according to conservative evidence bounds, separate from heuristic quality estimates. Data-loss resync invalidates recorded observation indices and may lower science/request results; it does not reveal required truth. Log nulls and uncertain values are intentional. The final geometry check uses the learned offset estimate, not hidden actual offset. Event durations use public-data predictions, not exact future weather.

The 900 budget is **normalized CPU seconds**, charged during agent turns. Own process CPU / `speed_factor` estimates normalized charge; `remaining_real_cpu_seconds` converts the remaining budget to machine CPU. Simulated exposure seconds, wall latency and model latency are separate. The local macOS Rosetta meter was reproduced undercounting CPU by 41.67×; comparisons use native arm64 runner, observer and calibration. The unmodified local meter also clamps aggregate CPU to wall duration and does not collect macOS child-process CPU. No numerical parallelism or new observer subprocesses are introduced. Backend accounting remains authoritative. A reserve reduces risk but cannot guarantee delivery after the backend budget expires.

Final score components, CPU profiles, ablations, held-out public-card results and limitations will be added after evaluation. Public L3/L4 held out from tuning are not blind hidden competition tests.
