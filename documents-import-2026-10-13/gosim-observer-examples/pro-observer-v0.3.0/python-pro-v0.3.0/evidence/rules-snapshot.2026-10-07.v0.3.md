# GOSIM Survey26 rules snapshot — v0.3

Snapshot: `survey26-2026-10-07-v0.3`; sources retrieved/inspected 2026-10-07. This version preserves the original v0.1 evidence below and incorporates the uploaded-artifact v0.2 addendum. It is an evidence update, not a change to competition rules.

## Current interpretation and validation

- The verified definitions in the historical snapshot continue to govern the observer. Numeric values come from public initialization. Original Pro uses a `python:3.12-slim` manifest; the uploaded successor instead pins a Python image digest. These describe different artifacts and are not interchangeable runtime identities.
- The new v0.3 manifest declares JSONL v4. Its native Python 3.12 execution is verified; acceptance/execution of the pinned hosted image has not been tested.
- The integrated RC5 suite passed 103 regression tests, including geometry, supported square layouts, full request/visibility intervals, clipped durations, repeat scoring, required evidence and correction replay, CPU fallback, and unavailable/malformed advisory responses. The old v0.1 statement that new contract tests had not yet run is historical, superseded by these test artifacts.
- Native arm64 Python 3.12.14 is used for the matched original/attachment/candidate comparisons. Process CPU, normalized charged CPU and wall time are separate reported measurements. The observer remains single-threaded for numerical search; local process-tree/meter limitations are not used to expand its allowance.
- The requested allowance is 900 normalized CPU seconds per episode, with 20 seconds reserved by the candidate. The uploaded run declares 300 seconds and a different wall cap; the missing public-test card/configuration prevents exact reconciliation. Both facts remain recorded.
- Local evaluation is performed with unchanged official engine files and public cards. The observer sees only public protocol input. No hidden hosted score, hosted-image performance, or score guarantee is inferred from these runs.
- Current evidence and commands: `tests/README.md`, `benchmarks/README.md`, `../pro-evaluation-v0.3.0/REPORT.md` in the delivered bundle. Native meter probes and exact source hashes remain in the audit artifacts; relative locations in the historical sections describe those original artifacts.

## Still unresolved

The exact uploaded `v4-public-test` card and launch configuration; a proven source/result identity for the two ZIPs; runtime identity/acceptance of the pinned hosted image; deployed engine revision and hidden-card results; exact raw quality/factor/required truth where the public protocol provides only rounded scores. The observer logs uncertainty rather than manufacturing these values.

---

## Preserved v0.1 source and definitions (historical)

# GOSIM Survey26 rules snapshot

Snapshot version: `survey26-2026-10-07-v0.1`
Retrieval date: **2026-10-07, Asia/Shanghai**.
Status: current official documentation verified; local runtime hash verified; deployed engine revision not independently verified.

Sources:
- [Official Survey26 documentation](https://create.gosim.org/survey26/platform/docs)
- [Retrieved documentation application asset](https://create.gosim.org/survey26/platform/assets/DocsPage-CgN7Hdkq.js)
- Local `docs/participant-guide.en.md`, `runner/challenge/`, `runner/project_platform/`, and `python-pro/observer.project.json` / `pack_agent.py` under `/Users/jqwang/Documents/gosim-observer-examples`.

The public runtime initialization governs numeric card values. Skill placeholders and astronomy analogies are not verified rules. All 17 local engine files match the supplied `ENGINE_MANIFEST.json`. Most entries identify revision `db4bddf3cc67fb5f0036d9fb2cf90b9e2b7e8f4a`; `fair_clock.py` and `v4_workflow.py` identify only the literal label `fair-clock`. This label is not a resolvable Git revision in this export; hashes are the precise evidence.

## Exact numerical definitions

For each valid target exposure, `g = min(flux * actual_duration * Q / (flux_zero_point * exposure_zero_point_seconds), 1)` and `c = science_weight * g * program_multiplier`. Quality is `sum(piece_duration * permitted * efficiency * transparency * sky_quality * lunar_factor / seeing / normalized_airmass^beta) / (q0 * actual_duration)`. Pieces split at slot/event boundaries and at most 120 seconds, evaluated at their midpoints; closed pieces contribute zero and remain in the denominator.

`S = sum_i max_valid(c_i) - required_missing * required_penalty - uniformity_weight * (1 - Jain) + request_reward + report_settlement`. Required/coverage thresholds use independent `max_valid(g_i)`. With populated RA-band completion fractions `r_b`, `Jain = (sum r_b)^2 / (number_of_bands * sum r_b^2)`; zero completed fractions give Jain zero. No exposures accumulate raw progress. `running_total` is only the science sum.

## Packaging and submission boundary

The supplied manifest specifies a complete JSONL-v4 project, `python:3.12-slim`, `python3 -u agent.py`, no build dependencies. The supplied packager places the manifest at ZIP root and excludes `.env`, credential-bearing env files and caches. Correct/false `report` actions concern instrument faults; they are unrelated to uploading or submitting scores. The engine settles scores automatically. No remote upload or evaluation was performed. Current deployed ZIP acceptance/ranking details beyond the supplied manifest/packager remain unverified.

## Retrieval and provenance

Current https://create.gosim.org/survey26/platform/docs fetched by authorized read-only curl after web accessibility and sandbox DNS failures. SPA app-build-time 1791358733260; index-BmX80Oe3.js references DocsPage-CgN7Hdkq.js, which embeds English documentation in variable v. Extracted without executing application code. English content exactly matches local docs/participant-guide.en.md after replacing only __BASE_URL__media/docs/v4-guide/ with images/. Evidence saved beside this file. Retrieval 2026-10-07 Asia/Shanghai. No repository Git revision available in exported project; use SHA256:

- local docs/participant-guide.en.md: f4ef9c5e3b1198fe99380dae6b8cc9620b52de0d901b9f76d982d599ebd9e832
- extracted live English guide: a375b22c96ce8a28479477a2c0942995c6017176d15947bf9589864a94fc7e6e
- runner/challenge/v4_scorer.py: 46154188eb409fb8408845d0a40ea07c143e1bb1f297f7ee79ab1559ac24cd66
- runner/challenge/v4_runner.py: 390cc6e7fa0a4ff31fa76fe4485511c026ee3355b3c4c203afea471e6a55af4d
- runner/challenge/v4_fiber_map.py: 9ac7ffd1d865d7c5bc999e554ae9516d208980d948d39223d9f0a047f2d72892
- runner/challenge/fair_clock.py: ccc690f6f4599757eb5e98980d24d73be427242accafae8d31f43078be8eee1e
- runner/challenge/v4_workflow.py: a50cd2d8f8ed8232aa7b764627db1cfc3acc532507a0e317684ed5adb436b73a

## Verified definitions

Line citations below refer to local files relative to BASELINE_ROOT. Live guide has same lines.

1. Score = sum target best valid contributions - required missing penalty - U(1-Jain) + completed request rewards + report settlement. running_total includes ONLY science best contributions (guide:344,643-660; runner:837-849). Ordinary target class adds no multiplier (guide:30). All numeric example constants must be read from initialize.
2. Exposure factor g=min(flux*T*Q/(f0*T0),1); contribution c=weight*g*program multiplier. Repeat observations never accumulate; best contribution=max c, required and uniformity state use separately max RAW g. Their maxima can belong to different exposures (guide:603-610,643; scorer:444-460,504-539).
3. Required satisfaction: some valid exposure g >= scoring.required.observed_factor_threshold, inclusive. Uniformity same type of independent threshold using scoring.uniformity.observed_factor_threshold and RA bands from public width. Jain zero when all ratios zero; only populated bands participate (guide:643-651).
4. Requests require actual exposure interval wholly within [issued_at_utc,deadline_utc], inclusive bounds; each listed target counts once after one raw g >= request threshold; successes need minimum_completed, then full one-time reward; no partial credit, unmet requests zero penalty. Overlap may satisfy multiple requests concurrently. Historical science best outside interval does not complete request. Deadline settlement can later be revised by data loss (guide:518-527; scorer:462-501; runner:579 onward).
5. Declared integer duration [60,3600] example; actual truncated exposure may be <60. Stops at same-night observing end and episode end. Full-exposure target altitude >=minimum_altitude required; failing at any point invalidates whole target exposure, while closures inside exposure merely contribute zero integral (guide:176,610; runner:709-785; fiber-map:min_altitude_during computes exact endpoints/lower culmination).
6. Quality integrates weather-slot/event splits then <=120-second midpoint pieces: normalized mean of observable_indicator * efficiency * transparency * sky_quality * target lunar factor / seeing / target airmass^beta divided by q0. Closed segments remain in full duration denominator. Program-band quality is separate, excludes efficiency and directional-event factors; weather slots then <=120 midpoint pieces, per-target moon and airmass. A single program may bonus only some targets; DARK/BRIGHT/BACKUP boundaries and multipliers public runtime config (guide:585-631; scorer:band_quality and score_target_exposure).
7. Fiber grid n^2 positive perfect square, area>0, gap>=0; row-major nr+c, row +alt and column +az. Actual tangent-plane GNOMONIC projection at exposure start, explicit zenith az orientation. Cell center offset (index-(n-1)/2)*pitch; glass square side sqrt(area), pitch=side+gap. Seams one cell, edge inclusive, gap frames excluded. Assign each target once and each fiber once; wrong fiber/outer target gives zero without geometric penalty. Hidden offset adds directly to alt/az then wraps az. Classification only at start; tracked thereafter, target altitude and quality vary (guide:183-201; runner:718-785; fiber-map:classify_offset/tangent_offsets/classify_target).
8. Modeled visibility: explicit night calendar with retained UTC quarter-hour slots; Sun example -18°, target example >=30° entire interval. Moon affects quality, not hard exclusion. No slew, setup, readout, teardown or rotator overhead in runner observation path. No basis to impose unmodeled astronomy constraints. Observe outside available night data has zero quality (runner:709 onward). Wait incurs opportunity cost only.
9. Resync invalidates observe action indices [floor(iN),floor(jN)), N frozen at delivery after any in-flight exposure finishes; wait/report do not increment observe index. Time not refunded. Recompute valid best, request progress and possibly expired request settlement. Resync returns best_scores and observed IDs, NOT max factors or required status (guide:775-812; runner:526-579). History cannot exactly recover g from rounded score unless program multiplier is known: per-target band is hidden and last_result gives score only. Therefore bounds/uncertainty are necessary where no exact mapping established; do not claim authoritative reconstruction solely from best score.
10. Budget 900 NORMALIZED CPU seconds per card; charge CPU/speed_factor only agent turns, aggregate cgroup processes/threads; API/network wait and engine time excluded. Larger speed_factor slower machine; reported remaining_real_cpu_seconds=remaining normalized budget*factor. Calibration pauses agent initially/~60 secs. Real cap 30 min default; no per-turn timeout. Field named global_wallclock_seconds despite CPU meaning (guide:276-281,345,746; workflow:51-53; fair_clock).
11. Protocol v4 action choices observe/wait/report/finish. Observe alt[0,90], az[0,360), known target IDs, legal integer fiber IDs and unique assignments; optional program default BACKUP. Extra fields beyond envelope or allowed action invalid; response cap512KiB excluding newline. Wrong protocol/sequence, nonfinite numbers, malformed JSON, duplicate normalized fiber ID e.g.5/05, or excess consecutive reports terminates agent_error; invalid action not settled; prior valid history settled. Wait duration same integer bounds, or until_utc later than now with Z; long until wait internally split. No general action-count cap found; report consecutive cap example32. survey_complete/agent_finished/global_wallclock_expired/agent_error final reasons, grace_seconds example30 (guide:668-761).
12. Report is instrument-fault diagnosis/repair, NOT score submission. Correct report immediately repairs extant unrepaired fault and earns example100; first2 false reports since last correct free, later example-150; false allowance persists through wait/observe; consecutive counter resets by wait/observe, correct reports count. Report uses zero simulated time; scores automatically finalized, finish voluntary. Current guide does not specify online upload packaging/ranking aggregation; project README/Docker instructions must supply packaging, avoid treating report action as final submission (guide:546-584).

## Conflicts and limits

- Current official prose says all process/thread CPU charged, but local fair_clock.py:207 clamps measured CPU delta to wall turn duration via min(window,...). Concurrent aggregate CPU could exceed wall and thus be undercounted locally. Local fallback without meter uses wall as CPU; charged_wait optional mode charges waiting (default remains cpu). Keep observer single-threaded and record clock_mode/cpu_meter; do not exploit discrepancy.
- No live deployed engine source inspected; local engine provenance verified separately by parent. Numeric card contracts always authoritative over example guide constants.
- Exact raw factor, required satisfaction, observed quality, and program band not supplied by ordinary last_result; predicted quality is an estimate, logs must distinguish predicted from inferred/realized. State resync explicitly acknowledges missing raw factors.
- No supporting qplan/PFS code needed for rules extraction; their instrument-specific values never used.
- Findings above confirmed by code inspection and current documentation, not yet reproduced by newly executed contract tests. Parent's baseline run and planned targeted probes should supply test evidence.

## Reproduced macOS/Rosetta CPU-meter discrepancy

A controlled CPU busy loop with 0.3, 0.6 and 1.0 seconds measured by time.process_time and resource.getrusage reproduces a substantial architecture-dependent local metering defect. Native arm64 Python reports mach_timebase_info=125/3; fair_clock._darwin_cpu agrees with both independent CPU measurements to <0.006%. The x86_64/Rosetta /Users/jqwang/anaconda3/bin/python3 reports timebase=1/1, but proc_pid_rusage returns the same native hardware tick convention. _darwin_cpu/time.process_time is 0.0240016, 0.0240015 and 0.0240006 respectively, approximately 3/125. Therefore the local runner undercounts CPU by 41.6667x when run under this Rosetta interpreter. Source location: fair_clock.py:449-479. Probe scripts and JSON results saved as darwin_cpu_probe.py, darwin_cpu_probe.json (arm64), darwin_cpu_probe_rosetta.json (x86_64).

The initial Rosetta baseline L1 local clock cpu_seconds=4.519 must not be reported as actual CPU or taken as proof of low computation cost. Approximate architecture-corrected CPU=188.292 seconds, subject to local rounding/turn-accounting; use the independent process CPU wrapper for exact measurement. No official runner code changed. Separately, ProcessAgent.cpu macOS reads only direct PID, unlike Linux tree accounting; future subprocess workloads could be omitted even with native interpreter. Keep both issues separate from observer optimization, document measured CPU and normalized estimated budget with meter provenance.

## Native-run cross-check

An unchanged native-arm64 L1 run completed with total 6236.572199, 154.376 measured process CPU seconds and 192.309 normalized charged seconds out of 900. The native, Rosetta and independently timed runs produced byte-identical actions/decisions. Rosetta figures are retained as evidence of a measurement defect and must not be used as true CPU cost. This verifies one public fixed-effort no-model baseline, not hidden-card performance or any proposed improvement.

---

## Preserved v0.2 uploaded-artifact addendum

# Survey26 rules evidence addendum v0.2

Inspected 2026-10-07. This supplements `../pro-successor-v0.1-audit/rules-snapshot.md`; it does not replace verified engine behavior with attachment comments.

## New primary run evidence

Source: user-supplied `observer-result (1).zip`, SHA-256 `4a983d7c6aa7971e68a0af279df8a2accf4c0b987ae439f6249ebc715d991b28`. Member `workflow_result.json`, SHA-256 `a5226f998d240c5f80385a7185cf7a511e94dc28b8702334ed0baab29620838e`.

The report declares scenario `v4-public-test`, protocol `participant-agent-protocol-v4`, fair-clock-v1 CPU accounting, a 300-second normalized budget and a separate 10800-second hard wall cap. It consumed 15.393 charged seconds, 14.567 process CPU seconds, and 26.952 wall seconds. The termination reason is `survey_complete`, with no hard cap reached. Model waits are reported separately at 11.599 seconds. These are facts about this reported run; they do not revise the user's requested 900-second evaluation allowance.

The supplied local engine, executed for matched L1/L2 comparisons with `--wallclock 900`, instead declares 900 normalized CPU seconds and an 1800-second hard wall cap. A different scenario/run configuration is a possible explanation, not a verified reconciliation. The public-test task card and its launch configuration are absent.

## New source evidence

Source: user-supplied source archive, SHA-256 `bd1b293b660b8a30c6d1a7b1ddece4519b115840c26b4b912b0b7baa689c75d1`. Member `observer.project.json`, SHA-256 `7c028724290fa664e567e29702d13eb4d8adc3a0bf9f47e922a4d4cabeda4d97`.

The manifest declares `jsonl-v2`, while the supplied run report and current official guide use protocol v4. This is an unresolved manifest/runtime mismatch. Local source execution successfully responds to the unchanged v4 local runner; that alone does not validate the manifest for submission.

The manifest pins a Python image digest. That image was neither resolved nor executed. Native arm64 Python 3.12.14 was selected for all three matching local implementations because the attachment evaluates `int | None` annotations and cannot import unchanged under Python 3.9. The native CPU meter was checked against process CPU on this interpreter; evidence is in `native312-cpu-probe.json` and `runtime-evidence.json`. Native source runs are not exact container reproductions.

Neither archive carries a verified source-to-result identity. Filename hashes and mixed v5/v6/v7 code labels are not sufficient evidence of a release version. Every extracted member is identified separately in `archive-provenance.json`.

## Unchanged rule conclusions

Repeated exposures contribute the best valid observation score, not summed effective exposure. Required satisfaction uses valid raw-factor evidence and its configured threshold; timed requests require the full actual exposure interval within their allowed interval. Local fixes and probes use these verified definitions from the earlier official guide/engine cross-check.

The attachment's season heuristic discounts replacement time by remaining factor; the action scorer itself already uses marginal best score. Record the former as a planning-cost mismatch, not as proof that its authoritative score state accumulates repeated observations.

## Open questions

- Exact task card and official launch configuration for `v4-public-test`.
- Source revision/configuration that produced the supplied result, including model-advice effects.
- Whether the attached manifest's protocol declaration is accepted or normalized by current submission tooling.
- Runtime identity of the pinned image and any local/platform timing differences.
- Hidden official scores, which cannot be inferred from these public local runs.
