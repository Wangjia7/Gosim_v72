# Reproducible local comparisons

Use native macOS Python for both judge and observer; the harness sets the calibration PATH to the same native interpreter. The official runner and engine remain unchanged.

```sh
PYTHONDONTWRITEBYTECODE=1 /Library/Developer/CommandLineTools/usr/bin/python3 benchmarks/run.py --agent-dir /absolute/path/to/observer --card L1 --label baseline-fixed0
PYTHONDONTWRITEBYTECODE=1 /Library/Developer/CommandLineTools/usr/bin/python3 benchmarks/run.py --agent-dir /absolute/path/to/observer --card L2 --label state-off --set PRO_STATE_EVIDENCE=0
PYTHONDONTWRITEBYTECODE=1 /Library/Developer/CommandLineTools/usr/bin/python3 benchmarks/run.py --agent-dir /absolute/path/to/observer --card L1 --label adaptive --adaptive
```

Default search is fixed level 0; `--adaptive` selects normal adaptive pacing. `--set PRO_NAME=value` is repeatable. Every run disables the model, sets a 900-second official budget, uses a Python-source-only execution snapshot and a fresh isolated observer working directory, and excludes inherited shell credentials and source `.env` files. `--out` optionally overrides the output folder. Default outputs are sibling `outputs/pro-evaluation-v0.2.0/<label>/<card>`.

`benchmark.json` includes exact runner/observer command, settings, source/engine/all-card-file hashes, full official score report, completion status and wall timing. `summary.json` and `runner.stdout` retain the official local summary, including native CPU, normalized CPU, speed factor, wall time and termination detail. Official raw decision/observation/workflow artifacts and stderr are retained. `decision-log.jsonl` exists only for observer versions that support the sidecar.

The observer receives public protocol stdin and never opens card files. The unmodified evaluator reads the card. A run reports success only for survey completion, zero runner exit status unchanged execution snapshot hashes and unchanged card files. Budget exhaustion and other early termination remain explicitly incomplete. Output directories cannot be reused once `benchmark.json` exists.

Prior baseline L1 results may be reused with `reused: true`; the original summary is retained without inventing a new command or measurement. Local scores are debugging evidence, not official hidden-card results. Original source changes during a run are recorded separately; execution snapshot changes invalidate its success label.

Use `--project-root /path/to/gosim-observer-examples` and `--python /path/to/native/python3` on another machine. On this macOS host the default interpreter is the native Command Line Tools Python; elsewhere the harness uses its own interpreter. Run judges sequentially when comparing CPU cost.
