# Reproducing comparisons

Use native Python 3.12 for the observer, judge and calibration. Run these commands from the observer folder; substitute your actual absolute paths. Run judges sequentially to reduce timing interference.

```sh
python3.12 -B benchmarks/run.py --agent-dir /path/to/python-pro --card L1 --label original --python /path/to/native/python3.12 --project-root /path/to/gosim-observer-examples
python3.12 -B benchmarks/run.py --agent-dir /path/to/extracted-attachment --card L1 --label attached --manifest-settings --fixed-level-env V5_FIXED_LEVEL --python /path/to/native/python3.12 --project-root /path/to/gosim-observer-examples
python3.12 -B benchmarks/run.py --agent-dir /path/to/python-pro-v0.3.0 --card L1 --label candidate --manifest-settings --fixed-level-env V5_FIXED_LEVEL --python /path/to/native/python3.12 --project-root /path/to/gosim-observer-examples
```

Add `--adaptive` to each matching comparison for default pacing. `--set PRO_SEASON_REPLACEMENT=0` isolates the replacement-cost flag; other stage flags are documented with the implemented configuration. Fixed search tiers are diagnostic and do not prove adaptive results. Identical tiers across different algorithms are whole-policy comparisons, not identical search workloads.

Every run forces model-disabled operation, a 900-normalized-CPU allowance, no inherited credentials, a Python-source-only execution snapshot and a fresh observer working directory. `.env` is never copied. The manifest loader accepts only nonsecret policy settings; image/build directives are not executed. The observer receives public protocol input only. The unchanged engine reads the task card.

`benchmark.json` stores exact commands, accepted settings, manifest/source/engine/card hashes, source-preservation checks and full score/termination results. `summary.json` retains science, penalties/rewards, normalized CPU, process CPU, wall time and calibration. Raw official actions, observations and workflow artifacts are retained; supported versions also write `decision-log.jsonl`.

Default outputs are sibling `pro-evaluation-v0.3.0/<label>/<card>`; use `--out` to choose another directory. A directory containing a previous benchmark cannot be reused. Budget exhaustion and incomplete termination are reported as failures rather than successful scores. Native source evaluation does not claim exact reproduction of the pinned container or hidden platform scores.

## Completed rc2 full-budget refinement setting

The following command reproduces the settings of completed L1 total 6600.590852 / science 6401.038511, charged CPU 652.323. Extract the preserved pre-width-fix runtime into a fresh work directory, and use a fresh benchmark label/output directory. It loads the retained nonsecret attachment manifest settings, selects adaptive pacing, and explicitly pins the relevant stage settings. Exact CPU and score can vary with calibration and deadline truncation. This result has no paired L2 run and does not meet 30%.

```sh
mkdir /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/work/rc2-reproduction-source
unzip /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/python-pro-v0.3.0/evidence/pre-width-fix-source.zip -d /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/work/rc2-reproduction-source
/Users/jqwang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -B /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/python-pro-v0.3.0/benchmarks/run.py \
  --agent-dir /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/work/rc2-reproduction-source \
  --card L1 --label rc2-fullbudget-refine-reproduction \
  --manifest-settings --fixed-level-env V5_FIXED_LEVEL --adaptive \
  --python /Users/jqwang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  --project-root /Users/jqwang/Documents/gosim-observer-examples \
  --set PRO_EVENT_DURATIONS=0 --set PRO_SCORE_COLUMNS=1 --set PRO_GAIN_CACHE=1 \
  --set PRO_EXACT_TIME_PRICE=0 --set PRO_LEADER_REFINE=1 \
  --set PRO_SEARCH_WIDTH_MAX=20 --set PRO_SCIENCE_ANCHORS=64 \
  --set V5_DEEP_ANCHORS=48 --set V5_DEEP_DENSE=80 --set V5_DEEP_POOL=2000
```

The original complete settings, commands and source hashes are retained in `../../pro-evaluation-v0.3.0/rc2-fullbudget-refine/L1/benchmark.json`. Changing `PRO_EXACT_TIME_PRICE` is a separate experiment, not this reproduction.

**Search-width caveat:** rc2 labels/settings requesting width 12 or 20 do not represent that actual breadth: the preserved rc2 planner caps its applied multiplier at 5, while the agent logs the requested value and normalizes its cost estimate by that value. The completed scores remain valid measurements of that frozen implementation. The full-budget run's larger base limits (48 anchors / 80 dense seeds / 2000 pool entries) still broaden search relative to 24/40/1000. The live rc4 source has corrected applied-width accounting and density-bin handling, and is under evaluation; this reproduction deliberately executes the preserved rc2 source.

The preserved ZIP has runtime/manifest files only. The command uses the live benchmark harness by absolute path, while `--agent-dir` selects the extracted historical runtime. Choose a different fresh extraction directory if the example path already exists.

## Selected RC5 checkpoint: exact reproduction

Use the frozen source identified in `../../pro-evaluation-v0.3.0/checkpoint-freeze.json` and a fresh output label. This command sets every frozen nonsecret policy parameter explicitly; the harness independently forces model-disabled operation, bytecode-disabled execution, isolated credentials and a 900-normalized-CPU allowance. Replace only `--card` and the fresh label to validate another card; do not tune using L3/L4 results. Historical RC2 commands above continue to require their archived source. Native execution does not validate the hosted container image.

```sh
/Users/jqwang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -B /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/python-pro-v0.3.0/benchmarks/run.py \
  --agent-dir /Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/python-pro-v0.3.0 \
  --card L1 --label rc5-frozen-reproduction \
  --manifest-settings --fixed-level-env V5_FIXED_LEVEL --adaptive \
  --python /Users/jqwang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  --project-root /Users/jqwang/Documents/gosim-observer-examples \
  --set PRO_EVENT_DURATIONS=0 \
  --set PRO_EXACT_TIME_PRICE=0 \
  --set PRO_LEADER_REFINE=1 \
  --set PRO_SCIENCE_ANCHORS=64 \
  --set PRO_SEARCH_WIDTH_MAX=20 \
  --set PRO_WIDTH_AWARE_GATE=0 \
  --set V5_DEEP_ANCHORS=48 \
  --set V5_DEEP_DENSE=80 \
  --set V5_DEEP_POOL=2000 \
  --set V5_FIXED_LEVEL=-1 \
  --set V5_OPTION_HEDGE=0.9 \
  --set V6_DESI_HA=0 \
  --set V6_DL_FAULT=0 \
  --set V6_DL_FLAT=0 \
  --set V6_DL_HORIZON=1 \
  --set V6_DL_REQ=1 \
  --set V6_DL_WEATHER=0 \
  --set V6_FAULT_DEEP=1 \
  --set V6_FAULT_FIX=1 \
  --set V6_GROUP_REQUESTS=0 \
  --set V6_LP_EVENTS=0 \
  --set V6_LP_MOON=0 \
  --set V6_LP_WEATHER=0 \
  --set V6_POINT_MODEL=0 \
  --set V6_REWARD_SPLIT=0 \
  --set V7_API_ASYNC=1 \
  --set V7_API_POLICY=tiered \
  --set V7_FAULT_MH=0 \
  --set V7_FAULT_U=off \
  --set V7_FREE_POLICY=v5 \
  --set V7_MODEL_EFFORT=auto \
  --set V7_NIGHTPLAN=on \
  --set V7_NIGHT_WAIT=8 \
  --set V7_PAID=v5 \
  --set V7_QA0=0 \
  --set V7_SHADOW=1 \
  --set V7_SHORT_API=0 \
  --set V7_SPLIT_EV=0 \
  --set V7_TURN_PRIOR=0.172 \
  --set V7_WAIT_SKIP=0 \
  --set V7_WALL=1
```

The lambda .45 / kappa 1 defaults are part of the frozen source; explicit equivalent ablation overrides are `--set PRO_LAMBDA_FRAC=0.45 --set PRO_KAPPA=1`. Each completed run retains full component scores, normalized/process/wall time and preservation hashes; regenerate the consolidated tables with `python3.12 ../../pro-evaluation-v0.3.0/collect_results.py` when running from this observer folder.
