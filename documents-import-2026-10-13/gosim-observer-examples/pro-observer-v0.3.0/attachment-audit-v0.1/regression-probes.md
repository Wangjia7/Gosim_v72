# Attachment: isolated regression probes

The probes use synthetic public fixtures, native arm64 Python 3.12.14, an empty inherited environment, rules-only mode, and direct imports from the extracted attachment. They do not run `agent.main`, contact an API, read card/truth files, or run a full judge. Source hashes before and after execution match. See `probe-results.json` for exact actions, module provenance, runtime and hashes; `probe_attachment.py` accepts the extracted source directory as its optional first argument.

Command from the workspace root:

```sh
env -i PATH=/usr/bin:/bin OBSERVER_MODEL_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 /Users/jqwang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/attachment-audit/probe_attachment.py
```

Native Python 3.9 initially failed during attachment import because `dutylog.py` evaluates a `type | None` annotation without postponed annotations. No compatibility shim was used. This is a Python-version limitation, not a reported failure of its intended Python 3.12 runtime.

## Reproduced

| Finding | Result and control |
|---|---|
| Incomplete anchor footprint | Two targets classify exactly into fibers 0 and 15 of one field. Their separation is 2.682791°; the anchor query radius is 2.138854° and returns only target 0. Restricting search to one anchor and disabling density seeds selects one target. Increasing only the diagnostic query radius to 3.5° selects both at the identical pointing, duration and program. |
| Shifted query coverage | A target classifies into fiber 15 of a shifted center. The original anchor query omits it; a fresh query around the shifted center includes it. This proves pruning inconsistency; it is not a full refinement-search performance comparison. |
| Score mistaken for raw factor | A possible valid raw factor 0.61 with score 6.1 becomes 0.508333 after resync. The configured required threshold is 0.6 and no configurable required-threshold attribute is loaded. Best-score evidence alone cannot identify the hidden multiplier. |
| Required threshold hard-coded | With configured threshold 0.6, matching DARK score 6.6 implies raw factor 0.55. Resync retains factor 0.55, but the gain branch `factor < 0.5` considers it no longer unsatisfied. The target is still required-unsatisfied under the supplied rules. |
| Short visibility omitted | A target above the planner safety limit for 100 or 450 seconds yields no action under normal limits. A diagnostic control lowering only the visibility floor and limiting durations to 60–90 seconds returns a legal 90-second observation. The control isolates short-window feasibility, not its expected score. |
| Timed reward ignores full interval | With an allowed 900-second exposure, deadlines at 600, 899, 900 and 901 seconds all produce the same action, request proxy 1000 and selected utility 2530. The first two intervals cannot earn official request credit; equality at 900 can. Ordinary science remains legal after a request deadline. |
| Replacement cost treated as accumulation | Default option pricing at factor 0.8 has one-fifth the modeled time demand of factor 0 for the same target and geometry. A new best-observation replacement still needs the full exposure; its marginal value decreases, rather than its exposure cost becoming 20%. The attachment's `desi_design` correction is disabled in the default probe. |
| Same-night allocation stays stale | After initial pricing, resync and another `plan` call in the same night leave `long_dirty=false` and the old option-price vector unchanged. The corrected score/factor state does not trigger immediate default season repricing. |

These probes demonstrate rule or cache mismatches. They do not measure how much each fix changes a full-survey score.

## Confirmed by inspection, not exercised here

- Refinement reuses the original `best_near` instead of querying its new center.
- The agent processes resync messages before last-result feedback; `_resync` clears pending predictions, so the later result cannot train the normal result path.
- Required evidence has no replayable valid-observe-index ledger and still conflates estimated raw factor with best score.
- Request reward proxies are uncapped across selected targets and merge independent overlap thresholds.
- There is no global deadline check inside pointing, exposure or season-price loops; pacing estimates alone cannot guarantee reserve preservation.
- Candidate duration/program selection assigns each target its predicted matching multiplier, then chooses one program afterwards.
- Final rounded/compensated actions lack the successor's exact recheck, and clipped terminal exposures shorter than the declared minimum are discarded.

## Unverified

Whole-survey effect, official platform performance, the retained ≥30% acceptance threshold, model-enabled behavior, malformed-service recovery, optional request-group overlap behavior and optional weather/pointing variants remain unverified by these tiny probes. No conclusion of superiority follows from their successful execution or from a score obtained under a different CPU budget.

## Smallest backport sequence

Retain the attachment's existing module layout and season architecture. Backport exposure/budget legality, actual-center geometry queries, evidence-before-correction replay, full request intervals and program-aware assignment from the approved successor. Then correct default replacement costs and invalidate season pricing on every relevant correction. Reuse existing synthetic/official-contract regressions and add the two season cases above before matching-input 900-normalized-CPU comparisons.
