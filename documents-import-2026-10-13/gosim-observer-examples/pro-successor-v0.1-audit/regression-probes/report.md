# Read-only regression audit

Run: `PYTHONDONTWRITEBYTECODE=1 python3 work/regression-probes/probe.py`. Output: `result.json`. Source baseline: `/Users/jqwang/Documents/gosim-observer-examples/python-pro`. No baseline or engine source edits; imports disable bytecode. Synthetic fixture uses official 16-fiber no-gap geometry (area0.4), with synthetic site/time/catalog and simplified sky/scoring to isolate mechanisms. Resync test imports official L1 program scoring. CPU timings measure individual calls with `time.process_time()` and are machine dependent.

## Reproduced through original functions

- `planner.py:861` (constant at65): two targets exactly on fibers0/15 in one field, angular separation2.682793degrees, declination difference2.680622degrees, margins0.316228. Original anchor query returns only target0. Controlled full `Planner.plan` radius2.1 emits `{0:T0}`; radius3.5 emits `{0:T0,15:T1}` at identical pointing `(59.9733,30.0518)`, program DARK, duration300. Controls set module constants N_ANCHORS=1,N_DENSE=0 only inside probe and restore them; radius is the only between-control change. Approx CPU0.6–0.8ms per search. This does not measure whole-survey score.
- `planner.py:792` (limits read132–133): instrument minimum1000 emits300; maximum200 emits3600. Official `runner/challenge/v4_config_check.py:106–110` accepts both configured ranges, verified by actual `validate_fiber_config` calls.
- `planner.py:655,684` (cutoff70): target remains above planner safety altitude for450seconds; baseline returnsNone. Probe-local MIN_VISIBLE_SECONDS=100 control emits300seconds, then restores constant. Start altitude22.186015; altitude after200seconds21.481982, above20.6degree safety limit. CPU of rejected original0.026ms.
- `planner.py:821`: 2×2 layout level3 uses anchor fiber5 outside n4 and returnsNone; same fixture level0 emits300seconds. Actual official validator accepts n4 (`v4_config_check.py:98–101`). This proves reduced-search coverage loss, not emission of an invalid assigned fiber.
- `planner.py:348–355`: historical factor0.55 at weight10 with official mismatch1.0 has score5.5; resync divides by top DARK multiplier1.2, estimating0.4583333333333333 and crossing required0.5 threshold. Official L1 program values read from `local-cards/L1/config/v4_score_config.json:17–22`. Public resync does not supply raw factor or required-completed IDs; exact truth cannot generally be reconstructed from scores.
- Level4 original `Planner.plan` still emits900seconds, approximately0.06ms CPU. This reproduces level4 search, with exhausted-budget selection separately established by source inspection.

## Inspected, not independently reproduced

- `planner.py:802`: ranking time price divides by literal16 despite variable grid.n.
- `planner.py:872,883`: refinement reuses best_near from original anchor query.
- `agent.py:265–266`: cpu/wall below15 selects level4, including zero/negative budgets. No direct `_pace` end-to-end budget probe was performed.

No credential access, service requests, full runs, or implementation fixes were performed.
