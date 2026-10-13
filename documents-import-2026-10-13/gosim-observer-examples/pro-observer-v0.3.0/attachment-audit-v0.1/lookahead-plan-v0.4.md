# Optional two-exposure planning experiment v0.4

Status: proposed; not implemented. Preserve all original, attached and v0.3 sources. This is a bounded scheduling experiment, not a promise of 30% improvement.

## Evidence and reason

The matched v0.3 no-event L1 run spent 425.542 occupied fiber-hours on observations that were later replaced or redundant in the final best-score history. Estimated saturation excess was another 549.897 fiber-hours; their union was 30.99% of occupied fiber-time. These are offline diagnostic quantities, **not recoverable telescope time**: all fibers share exposure duration, geometry limits substitutions, and earlier observations can teach the quality model. The repeated best-score replacement rule makes an early partial observation costly when a later full observation replaces it.

A local fixture illustrates an opportunity: a bright target and a faint target share a fiber. A long exposure can prefer the bright target's larger immediate score, although observing the bright target briefly and the faint target for longer could achieve more total score over the same two-exposure opportunity. One-step per-cell maximization does not account for that alternative. Wider search and the existing event grid do not change this underlying horizon.

Current measured improvements remain far below 30%. The largest previous full-run gains are documented separately; this diagnostic does not establish that two-step planning will close the gap.

## Smallest bounded experiment

Create a separate `python-pro-v0.4.0` candidate from the measured v0.3 source. Keep the existing modules and action protocol. Main change: an optional nested helper in `planner.py:plan`, with configuration and logging in the existing agent/logger only if necessary.

1. Keep the original legal incumbent and its full current utility.
2. Only inspect at most three leading fields after the usual search. Compare at most three first durations and two short/long second durations; use existing per-target score caches and a strict remaining-turn CPU allowance.
3. Form a modeled two-exposure science return using the official maximum-best-observation rule. For a target appearing twice, count only its larger resulting best contribution above the current authoritative best score. Within each exposure enforce one target per fiber and one assignment per target.
4. Compute the second pointing/targets at the future public sidereal time and check exact modeled fiber reachability, full visibility, night/episode endpoints and duration limits. Quality evolution is a declared forecast, not hidden truth. Restrict to a short horizon.
5. Compare first-action alternatives on the same two-action horizon, including the current incumbent as a control. Account for actual observing duration with the existing explicit time price. Do not compare an optimistic two-action sum against a one-action score as if they were the same quantity.
6. Initially disable this experiment during active timed requests and immediate required-target rescue. This limits interference with hard obligations while the science-only hypothesis is tested. Future request credit stays zero unless its whole interval and completion conditions are modeled faithfully.
7. Execute only the first action, revalidate it against the latest state, then replan from authoritative feedback. The second action is a forecast, not a command or a state update. Discard all temporary hypothetical scores after evaluation.

An additive flag defaults off. No model call, new package, random search, numerical thread or external optimizer is introduced. If a correct comparable-horizon implementation cannot fit this bounded scope, stop the experiment rather than silently introducing a global scheduler.

## Budget, tests and ablation

Use only the remaining search allowance after a legal action exists; reserve at least 20 normalized CPU seconds for the run. Interruptions return the original or improved revalidated incumbent. Record lookahead CPU, both forecast actions, current versus hypothetical best scores, modeled horizon/return, why the first action changed, and realized first-action science.

Regression cases: bright/faint targets sharing a fiber; repeated same target counted once; program mismatch across the two exposures; moving geometry and rising/setting boundaries; clipped final interval; early CPU interruption; no mutation of current best score/evidence/requests; fallback when a request or urgent required target is active.

Compare flag off/on on identical development cards and the same 900-CPU budget. Also report science, total score, obligations, repeat/saturation diagnostics and process/normalized CPU. Freeze a promising configuration before evaluating the held-out cards. Keep all negative outcomes. Rollback selects the untouched v0.3 candidate or turns the flag off.

## Impact requiring the user's original step-4 approval

This changes the scheduling horizon from one exposure to two, although module layout and public interfaces stay fixed. It adds temporary hypothetical score data and decision-log fields; it does not alter authoritative state definitions. It is a substantive scheduling change beyond the completed local-refinement experiment, so approval is requested before implementation.
