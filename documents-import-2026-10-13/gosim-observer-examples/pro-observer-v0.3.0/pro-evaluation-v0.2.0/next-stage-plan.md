> Historical draft before the user supplied the improved observer archives. Superseded by the attachment audit; not implemented or approved.

# Proposed next stage: rolling allocation inside the existing planner

Status: design only; implementation has not been authorized. Trigger: bounded duration, pricing, anchor and urgency changes fail the agreed ≥30% official total-score improvement over baseline on matching inputs under 900 normalized CPU seconds. This proposal does not predict that the threshold will be reached.

## Why consider a substantive scheduling change

L1 baseline total is 6236.572199; the acceptance target is 8107.543859. With the 300 request/report bonus points observed in the completed baseline run and no penalties, the target requires 7807.543859 science. The public catalogue's absolute science ceiling is 8517.6, because each target contributes at most its weight times the maximum program multiplier, 1.2. The ceiling is not an achievable schedule and does not prove feasibility.

Baseline science losses relative to that ceiling comprise 1979.9 points of incomplete factors among observed targets, 394.5 points among unobserved targets, and 105.9 points of program loss at the same attained maximum factors. Two required misses account for 100 penalty points; uniformity costs less than one point. These smaller components cannot independently close the approximately 1871-point total gap.

Baseline exposures occupy 234.8 of 244.25 observing hours. Their time-weighted fill is 12.436 of 16 fibers. Nonwinning repeated exposures consume 457.4 fiber-hours, or 15.7% of assigned fiber time; exposures beyond saturation consume another 15.8%, partly overlapping. These figures describe recoverable inefficiency, not a guarantee that all those hours can be reassigned usefully.

On 92 sampled successor pointings, unused fibers almost never contained an eligible target with positive marginal science at the chosen duration. Nearby shifts yielded only approximately 2–7% more science proxy. On 19 sampled states, broader science-oriented fields yielded approximately 20–42% more fixed-duration science proxy. That comparison used an optimistic model, omitted required/request utility, and did not simulate the resulting future state. Its implication is that a field's present score can compete with its future fragmentation cost; it is not a final-score forecast.

## Concrete change

Extend `_season_plan` from a once-per-night target completion mask into a periodically refreshed, short-horizon field/target allocation. Keep the existing immediate-action search and exact fiber classification. The allocation supplies soft preferences and time-price estimates to that search; hard action validity, visibility and timed-window checks remain authoritative at execution.

The current mask sorts targets by weight × flux and subtracts estimated target exposure needs from a pooled fiber-time capacity. It does not represent which targets can share a field, when those fields remain visible, or whether observing a target briefly now leaves a less efficient residual field later. The proposed allocation would explicitly model these relationships for a bounded candidate set.

A minimal deterministic formulation is:

1. Use existing value, science, required and request anchors to construct a bounded library of feasible field options across the current and next two observing nights. Each option contains a sampled start window, center, legal declared duration, expected actual duration, one declared program, exact unique-cell assignment and separate modeled science/required/request components.
2. Estimate each option's remaining best-observation contribution against the current authoritative science score and conservative required evidence. Exposure factors are not accumulated across repeated exposures.
3. Greedily allocate the largest modeled marginal return per unit observing time into the sampled windows, checking overlap and recomputing duplicated-target contributions. Protect bounded required and timed rescue options when their last feasible opportunity falls in this horizon.
4. Permit one bounded replacement pass: substitute an option or a pair of neighboring options when it improves modeled return while preserving protected rescue opportunities. No solver package, randomized search or numerical parallelism is proposed.
5. Give the immediate planner a completion preference for allocated groups, a soft cost for creating fragmented residual fields, and a science-derived time price. It may depart from the allocation when current public weather, request state or exact geometry makes another action better.

Initially avoid a persistent commitment to a particular future exposure. The allocation is an advisory plan, not an authority to declare targets complete or reserve unavailable wall-clock intervals. Unscheduled required targets whose deadlines lie beyond the short horizon retain existing season urgency; they must not silently disappear.

## Proposed files and functions

- `planner.py:_season_plan`: retain the existing implementation behind a flag; add the bounded rolling allocation and expose its modeled allocation summary.
- `planner.py:plan`: reuse candidate generation/assignment helpers for field options; apply the allocation preference after hard feasibility; immediately revalidate the returned action using the current synchronous state.
- `planner.py:remaining_opportunities`, `duration_candidates`, and request helpers: reuse their contracts; supplement opportunity counts with sampled feasible intervals where allocation needs them.
- `planner.py:on_result/_resync/on_requests`: mark the allocation dirty after new outcome evidence, corrections, request revisions or completion. Do not mutate the evidence ledger from allocation predictions.
- `agent.py:_respond/_pace`: supply the current public snapshot and the already established CPU/wall deadlines; refresh only when the bounded allocation budget permits.
- `decision_log.py` and existing decision packets: add an allocation identifier, public-state revision, option count, modeled components, refresh reason, preference contribution and spent CPU. QA remains diagnostic and cannot change allocations or actions.

Refactor only the few closures needed for reuse into private planner helpers. Do not introduce nine strategy modules or duplicate score/geometry implementations.

## Explicit impact flags

| Area | Proposed impact |
|---|---|
| Architecture | Existing agent/planner/geometry/QA layout retained; reusable private field-option helpers may be extracted. |
| Public interface | Official JSONL actions and decision sequence unchanged; additive `PRO_ROLLING_ALLOC` and bounded effort settings. |
| Data flow/state | **Substantive change:** a derived allocation cache depends on current public scores, required certainty, requests, weather notices, time and geometry. Corrections invalidate it. Predictions never become realized evidence. |
| Scheduling | **Substantive change:** future windows and residual field structure influence present ranking; the policy no longer relies solely on immediate return and a scalar season mask. |
| Exposure/scoring | Legal durations and best-exposure semantics unchanged; expected factors remain uncertain model values. Required relief and request benefit remain distinct from science. |
| Output | Additive allocation diagnostics and ablation records; no new official action fields. |
| Randomness/parallelism/dependencies | No additions; stable ordering and standard library only. |

This rolling future allocation changes the scheduler and its state-dependent data flow beyond the approved local fixes. That concrete expansion is the reason to seek implementation approval before coding it; difficulty reaching 30% is not itself an approval requirement.

## CPU and interruption limits

The official 900 normalized CPU seconds remains the hard run budget. Convert each snapshot's normalized remaining budget through the supplied real-CPU clock; do not infer normalized capacity from host wall time. Keep the existing end-of-turn reserve and deadline checks.

Initial caps: at most 64 field centers, three observing nights, six sampled feasible starts per night, eight durations per option center, three programs, 128 retained options and one replacement pass. Propose at most one normalized CPU second per refresh and at most 300 normalized CPU seconds for allocation over the run, additionally limited by the current per-turn deadline and remaining reserve. Track the allocation allowance as computation spent, not as simulator time. These are proposed starting limits, not measured production costs. Cap refresh CPU separately and stop at stage/loop boundaries with a valid immediate best-so-far action. Skip allocation refresh if its reserve cannot fit. If expired or invalidated, use the existing immediate policy rather than a stale allocation.

Refresh at night start and after a material correction/request change; otherwise at most once per simulated hour or a bounded number of observes. Choose the shorter update interval only when the measured benefit per CPU supports it. Record allocation CPU separately from immediate search and logging. Reserve enough budget to finish the survey under observed decision costs; spending the currently unused budget is not itself a benefit.

## Validation and regressions

Use unchanged official action validation and scoring code in tests. Synthetic fixtures should cover:

- Two fields with similar immediate gain: one leaves a sparse residual, the other preserves a shared completion exposure. Verify the allocation comparison and then the realized official best-score result.
- Repeated partial exposures cannot be combined to satisfy science, required completion or a timed threshold.
- Different targets in the same cell can replace one another as allocated duration changes; assignments retain target and fiber uniqueness.
- Required/timed rescue survives greedy allocation and the replacement pass; equality and ±1-second boundaries remain inclusive and rule-faithful.
- A configured minimum declaration clipped at the night or episode boundary remains legal; its actual interval controls credit.
- An outcome and a same-turn half-open invalidation revise the allocation once, using surviving evidence; expired request reward revision also invalidates dependent preferences.
- Changing public weather, program estimate, learned offset or score state cannot reuse a stale option. A public request revision with unchanged scalar reward must still refresh interval-dependent options.
- CPU interruption before/during refresh preserves a legal immediate response; deterministic replay produces the same action and allocation order.
- Optional QA output cannot change allocation, numerical state or actions.

Ablate against the strongest verified local successor, not an abandoned weaker intermediate: immediate policy → science-priced mask → rolling target allocation without fields → rolling field options → residual-field preference → one replacement pass. Retain L1/L2 for development and do not inspect L3/L4 during tuning. Use matching public inputs, no-model settings, native CPU metering and the actual 900-normalized-CPU cap. Report total and all official components, nonwinning repeat fiber-hours, saturation waste, useful time-weighted fill, action counts and allocation CPU. Compare whole-survey realized results; local surrogate gains do not establish acceptance.

## Rollback and decision gate

Default `PRO_ROLLING_ALLOC=0` until approved and validated. Disabling it restores the verified immediate scheduler; the original Pro export remains untouched. Keep allocation data separate from hit evidence so rollback cannot corrupt required or science state.

Proceed only after approval of the scheduling/data-flow expansion above. Accept the implementation only if it passes legality/state regressions, completes within the official CPU cap and meets the user's ≥30% official total-score criterion on the agreed matching evaluation set. If it does not meet that threshold, report the measured result and remaining gap without presenting the proposal or a model-derived ceiling as success.
