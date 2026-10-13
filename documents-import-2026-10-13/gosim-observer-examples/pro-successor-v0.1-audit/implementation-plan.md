# Pro successor: audit and approval plan v0.1

Date: 2026-10-07 (Asia/Shanghai). Status: **audit completed; observer implementation awaiting approval**.

## Baseline and boundaries

Use `python-pro` in `/Users/jqwang/Documents/gosim-observer-examples` as the baseline. `rust-pro/README.md` describes a line-by-line Python port; `typescript-pro/README.md` describes a module-by-module Python port. This resolves the version question without silently choosing a different strategy. The proposed successor is `python-pro-v0.2.0` under that same project root. The three original Pro folders remain untouched.

The distribution has no `.git` directory, so there is no available baseline commit, branch, Git status, or uncommitted-change comparison. `git status` failed with “not a git repository.” `provenance.json` records the file snapshot instead. Do not initialize a repository or imply this export is clean relative to upstream. Before implementing, verify the recorded hashes again and preserve any intervening changes.

All nine supplied skills plus README, manifest and source-map were read. Their contracts guide changes within the existing files; they do not justify a nine-module rewrite. DESI ledger/QA principles, QPlan hard-feasibility-before-ranking, and PFS pointing/assignment separation are used only as described in these supplied skills. No external QPlan/PFS implementation was used as evidence or added as a dependency.

Entrypoint: `python-pro/agent.py:450`, manifest `python3 -u agent.py`, Python 3.12 container, standard library only. Existing configuration is `PRO_*`, model variables and `OBSERVER_MODEL_DISABLED=1`; no new default model choice is implied by the requested GPT-6.1-Sol audit subagents. `pack_agent.py` is the existing packaging path. No test suite was found for Pro; the supplied runner and its hash verifier are the integration harness.

Preserve JSONL protocol v4, action fields, `decision_sequence`, standard-output purity, original `PRO_*` meanings, deterministic tie-breaking, and existing module responsibilities. No new runtime packages, random search, observer subprocesses, or concurrent numerical search are proposed. No upload, remote evaluation, or push is included.

## Observed loop

`main → ObserverAgent.respond/_respond → messages/resync → active requests → last result → _pace → night advice/report checks → Planner.plan → JSONL action`.

`Planner.plan` performs visibility pruning, value/density seeds, anchor-to-fiber centers, tangent-plane classification, per-cell target choice for each coarse duration, time-price ranking, local shifts, then one final program choice and hidden-offset correction. It already couples assignment with coarse duration and already uses best-observation marginal science, rather than cumulative exposure.

`Planner.on_result` learns score, estimated factor, sky quality, band and pointing offset. `_resync` resets best-score state and estimates factor from best score. CPU pacing uses process CPU and wall time separately, but measurements are per decision rather than by component. Existing model stages run at night boundaries/report confirmation; they are not per-step QA. Existing stderr logs are human-readable.

## Evidence-ranked findings

Evidence tags: **R** reproduced through unchanged baseline functions; **C** confirmed by inspection/current documentation; **H** plausible benefit not yet measured.

| Priority | Evidence and source | Finding |
|---|---|---|
| P0 | R: `planner.py:792`; official config validator accepts tested ranges | A minimum of 1000 emits 300 seconds; a maximum of 200 emits 3600. The duration grid does not honor both loaded exposure limits. Default L1 limits happen to contain it. |
| P0 | C: `on_requests:320`, `gain:748`, `quick:773`; live guide/engine | Request timestamps are discarded, so rewards can influence an exposure that finishes after the deadline. Such an exposure may still legally earn science; request credit alone must be zero. |
| P0 | R/C: `_resync:348`, `on_result:370`, `value:606`; live guide Appendix A | Required completion differs from best contribution. With default program multipliers, a valid raw factor 0.55 at weight 10 and score 5.5 becomes 0.458333 after resync. Ordinary feedback does not reveal the true multiplier/raw factor, so exact state is sometimes unknowable. Hard-coded 0.5 also ignores configurable thresholds. |
| P0 | R/C: `agent.py:245–266`, `planner.py:634,821` | Low/zero CPU selects level 4, but level 4 still searches. There is no in-search deadline or guaranteed budget reserve. `respond:147` records the level before `_pace` changes it, attributing the timing to the previous level. |
| P1 | R: `planner.py:65,861`; geometry probe | Two targets legally occupy fibers 0 and 15 in one pointing, yet the 2.1-degree anchor query omits one. Increasing only the probe radius finds both at the identical pointing, program and duration. An anchor query needs the anchor-to-center displacement **plus** the field footprint; one field radius is insufficient. |
| P1 | R/C: `planner.py:58,802,821`; `skymath.py:113` | Reduced search uses fibers 5/6/9/10, failing a supported 2×2 fixture; time pricing divides by 16. `OFFSET_STEPS=16` is a calibration-grid resolution and should remain independent of fiber count. |
| P1 | R/C: `planner.py:70,655,684,285` | A valid 450-second opportunity is removed by the 600-second prefilter. Season windows assume 20 minutes, rather than action-specific feasibility. Final pointing centers are additionally restricted to minimum target altitude/89°, although the API allows center altitude [0,90]. |
| P1 | C: `planner.py:792,872–883` | Fixed durations miss event boundaries; refinement defaults to the winner's duration and reuses its old neighbor list. Exact assignment-duration evaluation already exists and should be retained. |
| P1 | C: `gain:748`, `plan:895–905` | Ranking grants each target its own matching-program multiplier, while one action can declare only one program. Program is chosen afterwards; estimates can overstate the chosen action's science. Request reward divided by remaining count can also overvalue more targets than the request needs. |
| P1 | C: profile first 20 L1 exposures | 5,490 evaluations make 2,078,735 gain calls and 687,942 tangent projections. Geometry and repeated gain calculations dominate. Per-decision caching and selective refinement have a concrete cost target. Their score/CPU benefit remains H until measured. |
| P2 | C: `agent.py`, `advisor.py`, `llm_client.py` | No structured per-decision/outcome packets or retrospective entrypoints. Rules-only already works when explicitly selected, but missing credentials otherwise abort startup. Existing retries use per-attempt timeouts rather than a strict total-call deadline. |

The regression probes are diagnostic bug reproductions, not a claim that the baseline passes correctness tests. No whole-survey score gain from any proposed fix has been established.

## Smallest implementation sequence

Each stage has a separate feature flag where meaningful, a recorded diff and matching-input comparison. Rollback is disabling the stage or selecting the untouched `python-pro` directory; no destructive in-place rollback is needed.

### 0. Freeze provenance and measurement

Copy only the baseline source/configuration/package files into `python-pro-v0.2.0`, omitting credentials, caches and build products. Include version/config hashes and the rules snapshot. Establish deterministic baseline commands, native CPU metering and regression assertions. Preserve the original runner exactly. The local Rosetta CPU-meter discrepancy is an environment qualification issue, not permission to edit the judge.

Files: successor version metadata/docs, tests and benchmark scripts; no scheduler changes. Skill: `budgeted-search`, orchestrator. CPU effect: measurement only.

### 1. Enforce action limits and budget exit paths — P0

Files/functions: `planner.py:plan`, `agent.py:respond/_pace/_respond/_to_next_slot` and the exception fallback in `main`.

Filter all declared observe/wait durations through loaded integer min/max; evaluate actual exposure duration after official night/episode clipping separately. A legally declared minimum exposure may be clipped shorter by the engine. Keep public action validity distinct from per-target/request credit. Measure the actual selected search level. Add configurable reserve and checks at stage/loop boundaries; retain a revalidated legal best-so-far action, or use legal wait/finish when no useful action fits. Bound the initial work needed before the first feasible candidate. A local CPU check estimates available time; the backend remains the authority and can stop the process before any fallback at actual exhaustion.

Skills: `budgeted-search`, `queue-scheduling`, `exposure-control`. Expected behavior: fewer invalid actions and budget overruns; no score-gain estimate. CPU: small checks, bounded tail work. Tests: min/max/integer limits, actual truncation, zero/tiny reserve, fallback with no feasible target, correct pacing attribution.

### 2. Correct footprint and fiber-dependent search — P1

Files/functions: `skymath.py:FiberGrid`, `planner.py:neighbours/plan/evaluate`.

Derive legal fiber IDs and central subsets from loaded grid geometry. Replace the pricing divisor with loaded capacity. Derive a conservative angular bound from the square glass/cell footprint; query around the actual center, or include anchor displacement and maximum refinement movement in the anchor bound. Requery shifted centers when needed; handle wrap/polar bounds conservatively, then apply existing exact gnomonic classification. Keep square-cell assignment; there is no evidence requiring a general matching/MIP solver for disjoint fixed cells.

Maintain bounded required and deadline anchor slots alongside existing value/density seeds; compare shifts by assignment utility. Validate compensated/rounded final commands. Skills: `pointing-candidate-optimization`, `fiber-assignment-optimization`. CPU: larger broad neighborhoods increase work, mitigated by deduplication and per-decision geometry reuse. Tests: outer/diagonal fibers, gaps/seams, rotated sky coordinates, supported small/large square grids, sparse required/timed seeds, offsets and shifted-center coverage.

### 3. Retain evidence through state correction — P0

Files/functions: `planner.py:__init__/on_result/_resync/value`, `agent.py:_respond`.

Keep science best contribution, estimated raw factor, raw-factor bounds and required-satisfaction certainty distinct. Save realized public hits by official `observe_index`, declared program and actual interval; derive conservative bounds from rounded scores and all possible supported multipliers. A threshold-crossing lower bound confirms satisfaction; an upper bound below threshold confirms insufficiency; otherwise label unknown. Direct request-completion evidence may tighten bounds only when its threshold and valid-history context justify it. Do not invent authoritative per-target fields absent from the protocol.

Record the previous outcome before applying data-loss invalidation, invalidate exactly the announced observe-index range, rebuild surviving evidence, reconcile authoritative best scores and active requests, and invalidate affected value/quality/offset caches. An authoritative science correction can lower science without proving required status. Keep heuristic factor estimates for quality learning visibly separate from evidence used to claim completion.

Skill: `survey-state-ledger` and DESI-style replayable evidence. CPU/memory: compact append-only hits, rebuild only on resync where feasible. Tests: best contribution and best factor from different exposures, ambiguous multiplier, repeated nonaccumulating exposures, rounding at threshold, survival/removal of the last exposure, repeated corrections, revised expired requests. Exact hidden raw quality remains unavailable.

### 4. Make timed opportunities and gain estimates rule-faithful — P0/P1

Files/functions: `planner.py:on_requests/_build_windows/plan/gain/quick`.

Retain each request's start, deadline, threshold, target set and remaining count. Evaluate full actual exposure intervals; invalidate only the impossible request benefit when ordinary science remains legal. Preserve separate overlapping-request thresholds and cap aggregate reward by the request's completion condition. Separate deterministic credit conditions from uncertain quality and the existing soft urgency terms.

Evaluate the selected assignment/duration with each available declared program for leading candidates; compute marginal best-score gain using matching/mismatch multipliers consistently. Log heuristics separately from expected official components. Replace universal 600-second visibility pruning with minimum useful legal exposure, then exact full-interval target checks. Estimate remaining night-window opportunities before adding soft scarcity ranking. No slew/setup/readout costs are added. Recheck the selected action against the current synchronous request snapshot immediately before response.

Skills: `queue-scheduling`, `exposure-control`, `fiber-assignment-optimization`. CPU: up to three program evaluations for selected candidates, request-set bookkeeping, bounded window checks. Tests: equality and ±1-second deadline/start boundaries, minimum_completed and overlap, partial success has no reward, setting/rising/episode endpoints, one program across mixed target bands. Rank changes are substantive and require ablation.

### 5. Add useful duration events within staged search — P1

Files/functions: `planner.py:plan/evaluate/gain`, narrow geometry helpers if needed.

Keep the existing coarse grid; add integer neighbors of estimated first useful gain, required/request/uniformity threshold, saturation, visibility/request/night/episode endpoints and program-band crossings where modeled. These are model-derived events, not exact forecasts of hidden weather. Recompute per-duration assignment and declared-program utility for leading candidates. Refine their centers and durations together with a hard effort cap.

Cache target-duration-program gain within one decision; cache target vectors and center basis where valid. Broader coarse search precedes expensive leading-candidate evaluation. Only consider shallow urgency lookahead after these stages demonstrate value per CPU; it is a separate optional ablation, off by default initially.

Skills: `budgeted-search`, `exposure-control`, pointing/assignment skills. Expected CPU: caching may offset wider search; measure instead of assuming. Tests: saturation, discrete threshold crossings, negative marginal repeat gain clamped correctly, duration-dependent target swaps, cache invalidation and budget interruption. No cumulative effective-exposure state.

### 6. Add structured records and optional retrospective review — P2

Files/functions: `agent.py:respond/_respond/main`, `planner.py:plan/on_result/_resync`; small new `decision_log.py` and `qa_review.py`, with bounded client changes in `llm_client.py` only if reused.

Emit an append-only JSONL sidecar for every action and a correlated outcome record on the next request. Include version/config/state hashes, action and observe IDs, selected pointing/fibers/duration/program, predicted components versus heuristic terms, quality estimates/bounds, required/request transitions, windows/slack, leading alternatives with stable rejection codes, and per-component process CPU, normalized budget snapshot, reserve and wall time. A run ending before feedback marks an outcome pending, never fabricates it. No new fields go into official action JSON.

Ordinary feedback gives realized science changes and some request/report events; final judge artifacts give the full score decomposition. Required/uniformity per-step truth and raw observed quality are unavailable and must be null/uncertain until valid evidence exists. Offline QA may join judge results after a local run; the observer may not read card truth at runtime.

Provide two CLI/API modes: whole-log analysis and individual completed decision/outcome review. Per-step mode supports offline replay or bounded event-triggered/asynchronous consumption of the sidecar. Every step is recorded, but no blocking per-observation model call is required. Review output is schema-validated diagnostics and experiment proposals with no state mutation or control authority. Environment-based provider/model/credential settings, bounded total time/retries/queue size, secret redaction and graceful malformed/unavailable-service handling are required. Explicit no-model mode remains; missing optional QA credentials disable QA. Any proposed change to the existing advisory startup behavior is documented and tested separately.

Skill: `observation-qa-retrospective`; loosely coupled QA. CPU: log serialization/write overhead measured; model latency/cost recorded independently. Existing nightly advisory threads may remain; no numerical parallelism is added. Tests: unavailable service, malformed/nonfinite/oversized response, retry deadline, queue saturation, secret-free packets, unchanged numerical action/state under different retrospective outputs.

## Explicit impact flags for approval

| Area | Proposed impact |
|---|---|
| Architecture | Existing agent/planner/geometry/advisor organization retained; two small QA/log helpers and external tests/tools added. |
| Public interface | JSONL action protocol unchanged; additive configuration and optional review CLI. |
| Data flow/state | **Changes:** outcome-before-correction evidence processing, observation history, certainty/bounds and cache invalidation. |
| Scheduling | **Changes:** geometry coverage, legal durations, request credit, remaining opportunities, program-aware gain, duration events and bounded effort. |
| Output | **Additive:** structured sidecar and QA schema. Existing protocol stdout remains intact. |
| Randomness | No added randomness; stable deterministic iteration/ties. |
| Parallelism | No added numerical parallelism; optional offline/event reviewer is isolated and bounded. Existing advisory threads retained where enabled. |
| Dependencies | Standard library only. No DESI/PFS/QPlan packages, solver package or service required. |
| Budget | Internal reserve/stage checks added; official measurement authoritative. Host CPU-meter discrepancy disclosed. |

## Validation and acceptance

1. Turn audit reproductions into assertions for the successor, with the original baseline demonstrating the old behavior. Run official protocol/action validation before interpreting score deltas.
2. Compare untouched baseline and each stage on identical public cards, inputs and no-model settings. Use fixed search levels for deterministic policy comparisons, then default adaptive pacing under the actual 900 normalized CPU limit. Verify the environment's CPU meter before accepting budget results.
3. Develop on L1/L2; retain L3/L4 from tuning. These are public cards with published baseline results, so “held out” means held out from our tuning, not blind hidden validation. Hidden official performance remains unverified until an authorized platform evaluation.
4. Ablations: baseline → action/budget guards → footprint/layout → state evidence → temporal/request/program scoring → event durations/caches → structured logging → optional QA. Also isolate state and temporal changes against baseline when causal attribution would otherwise be unclear. Keep lookahead separate.
5. Report total, science sum, required misses/penalty, timed completions/reward, uniformity, fault-report settlement, observed targets, actions, process CPU, normalized CPU, wall time, clock mode/meter and profile overhead. Include failures and per-card regressions, not only the mean.
6. QA tests use deterministic fake providers; real service comparisons, if later authorized, keep provider/model, latency and cost separate from policy CPU. Baseline and successor must receive equivalent advisory inputs for a causal comparison.
7. Promote defaults only after correctness, budget and paired measurements support them. Keep harmful/unproven optimizations disabled. Deliver runnable version, minimal diffs, source/rule hashes, test commands, raw comparisons, component profiles, log/review docs and unresolved assumptions. Never describe an implemented heuristic as a demonstrated score improvement without supporting measurements.

Approval requested for the scoped stages above before creating or editing successor implementation files. This approval gate is the user's explicit step 4 requirement.
