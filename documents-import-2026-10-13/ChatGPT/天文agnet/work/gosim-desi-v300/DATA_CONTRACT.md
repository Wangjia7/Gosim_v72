# Inputs and reproducibility

Production agent receives only stdin public initialize, active requests, bulletins,
forecasts and its own exposure results. No card-ID branches, file-based target
readers or hidden future weather/requests enter the numerical decision loop.

The local runner is copied byte-for-byte from Documents/gosim-observer-examples;
all 17 ENGINE_MANIFEST files verified. Offline catalog/weather/request generation
uses the saved official v4 generator family from work/observer-v101/engine. Copies
are under generator/challenge, and generation configs plus SHA256 inputs are
retained. Production ZIP excludes this generator, runner, inputs and results.

Synthetic seeds, scenarios and budgets are declared in case-manifest-v2.json and
matrix-plan-v2.json. Final numerical source is captured before its final regression scores in
request-guard-source-frozen.json. Temporal CPU pacing and OS calibration make exact action
replication machine-dependent; final totals are actual official-scorer outputs.

The first generator placed n_fibers and fiber_area_deg2 at the config root instead
of within field. Those retained cases actually used 16 fibres and 0.4 deg2 cells.
Their manifests explicitly record this error. Corrected cases live in cases-v2,
never overwrite original inputs, and final geometry evidence uses the corrected
matrix. Case names are only experiment labels; the planner ignores them.

Standard CPU budget is 120 for corrected synthetic runs and 180 for L1 comparison.
Both baseline and candidate use the same requested budget, inputs and scorer.
Model disabled for paired numerical runs; real API results are not claimed.
Weather RNG is Python random.Random/MT19937 in the official generator, paired via
identical on-disk products. No simulator/scorer formulas or truth are altered by
the agent. Matrix uncertainty is per-case evidence, not a statistically established
population mean or one-switch causal effect.
