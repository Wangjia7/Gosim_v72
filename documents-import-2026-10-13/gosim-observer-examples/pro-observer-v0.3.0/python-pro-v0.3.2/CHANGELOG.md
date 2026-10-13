# v0.3.2 platform manifest correction

Remove platform-owned OBSERVER_MODEL_DISABLED from the manifest (29 ->28 settings). Model mode is selected on the platform; absence of credentials still uses rules. The packager checks manifest field/schema/path requirements and rejects OBSERVER_* settings. Observer code and previously measured RC5 policy stay unchanged. Add a packaging regression for platform settings, schema and relative paths. Prior failed package versions remain preserved.

---

# v0.3.1 packaging correction

Fix the reported platform rejection by reducing manifest environment from 43 to 29 settings, omitting only source defaults. Add pre-pack validation for the environment object, <=32 entries and string names/values. Default output ZIP follows the project directory name. Numerical observer source and decision-log version stay RC5; no performance improvement is claimed. Original package and historical failed/negative experiments remain preserved.

---

# v0.3.0 experimental checkpoint — 2026-10-07

Parent: user-supplied attached source, archive SHA-256 `bd1b293b660b8a30c6d1a7b1ddece4519b115840c26b4b912b0b7baa689c75d1`. Approval: user's explicit acceptance of `attachment-audit-v0.1/implementation-plan.md`. No Git revision is available in either export.

- `planner.py`, `skymath.py`: full fiber footprint queries, exact final cell validation, state evidence/reconciliation, full request intervals, loaded duration/threshold limits, science and obligation anchors, cached joint program/exposure scoring, duration events and bounded center refinement. Existing attachment duty-log, pointing, weather and fault-related code remains.
- `season.py`: full replacement exposure demand, marginal science value from best-score state, same-night invalidation support and bounded auction iterations. No DESI instrument constants or external package imported.
- `agent.py`: outcome before correction, conservative derived-cache reset, legal reserve/fallback handling, normalized CPU reserve with current calibration, adaptive breadth, explicit soft/global deadlines and structured per-step logs. Existing report and advisory flows retained.
- `llm_client.py`: bounded total deadline, retries, response/request sizes and concurrent outstanding I/O; malformed/nonfinite responses and unavailable credentials fail gracefully. Secrets are redacted from diagnostics.
- New `decision_log.py`, `qa_review.py`: standalone structured log helper and optional offline/remote run, step and replay diagnostics, adapted from v0.2.0. Review has no mutation or control authority.
- `observer.project.json`: retains nonsecret attachment flags and pinned image; corrects protocol declaration to v4. Local native execution does not prove the pinned container identity.
- New packaging, regression tests, benchmark command, rules/provenance evidence and documentation. `pack_agent.py` excludes credentials, results and test/evidence material from the submission ZIP.

The normalized patch and per-file line counts are in `evidence/attachment-to-v0.3.0.patch` and `evidence/minimal-diff-summary.json`. The original source and archive remain unchanged. Five existing Python runtime files and the manifest are modified; ten original Python modules retain their original bytes. New helpers do not create a nine-module framework or add numerical parallelism/randomness.

Validation at initial freeze: 85 tests passed with native Python 3.12.14. Synthetic and official-engine assertions establish only the tested local behaviors. Full-survey comparisons, CPU profiles and ablation outcomes are separate evidence. Performance acceptance is not implied by this changelog.

## rc2 refinement candidate

After the initial paired checkpoint, add lazy score columns, an arbitrary-dependence geometric lower bound on the soft request progress proxy, corrected optional group-proxy cancellation and post-filter utility, plus opt-in multi-leader pointing refinement/exact time pricing. A bounded configuration can increase adaptive width to 20; default remains 5. Event durations default off based on measured checkpoint results. The current rc4 integrated suite passed 102 native Python 3.12 tests, including cache/no-cache decision parity and legal assignment improvement under a synthetic offset. The pre-refinement source is preserved in `evidence/pre-refinement-source.zip`; rc2 whole-survey results are separate.

## Measured status

The rc1 no-event paired result is L1 6551.839453 / L2 6746.161380, summed +1.31% versus the attachment and +6.51% versus original Pro. Separately, the best completed rc2 L1 result is `rc2-fullbudget-refine`: total 6600.590852, science 6401.038511, charged CPU 652.323/900, +2.96% versus attachment and +5.84% versus original Pro. It uses leader refinement, width cap 20, 64 science anchors, and deep anchor/dense/pool limits 48/80/2000. It does not enable exact time pricing. There is no paired rc2 L2 result yet, and neither checkpoint meets the 30% requirement. A proposed v0.4 substantive policy change awaits user approval; it is not implemented.

**Search-width caveat:** rc2 labels/settings requesting width 12 or 20 do not represent that actual breadth: the historical rc2 planner capped its applied multiplier at 5, while the agent logs the requested value and normalizes its cost estimate by that value. The completed scores remain valid measurements of that frozen implementation. The full-budget run's larger base limits (48 anchors / 80 dense seeds / 2000 pool entries) still broaden search relative to 24/40/1000. Current rc4 source includes the applied-width/cost correction and density-bin fix; its separate L1 comparisons completed and it is not the source of the historical rc2 scores.

## rc3 width and cost correction

Current frozen source applies the configured adaptive search-width cap (up to 20) instead of silently capping it at 5. Cost estimates and diagnostics use the applied multiplier. The rc3 full-budget L1 run terminated early with a request-triggered density-bin KeyError and is INCOMPLETE; its partial score is not a valid full-survey comparison. The RC4 integrated suite passed 102 tests in 0.433 seconds; its L1 comparisons completed. Current RC5 validation is described below. Historical rc2 measurements remain tied to `evidence/pre-width-fix-source.zip`, and do not establish the corrected source's performance. The 30% acceptance requirement remains unmet.

## rc4 density correction and bounded error locations

Exclude nonpositive-science density bins that have no representative, preserving protected active-request candidates. Add bounded exception-class/traceback-location diagnostics and three credential-exclusion/protocol regressions. Add the optional `PRO_WIDTH_AWARE_GATE` ablation, default 0, for deep-mode admission using width-normalized CPU/wall estimates. Integrated validation: 102 tests passed in 0.433 seconds before the final comment/logger-version-only delta. The failed rc3 run is INCOMPLETE and cannot be used as a full-score comparison. The preserved pre-density source is `evidence/pre-density-fix-rc3-source.zip`; RC4 L1 evaluation completed; RC5 L2 and prospective L3/L4 validation subsequently completed. No v0.4 implementation is authorized or included.

## RC5 retrospective alarm correction

Add a deterministic QA alarm for explicit `constraints.reason=INTERNAL_ERROR`; unknown feasibility alone remains non-alarming. Captured failed step 741 is diagnosed offline with no API call. Agent/planner scheduling policy is unchanged from RC4. Integrated validation passed 103 tests in 0.415 seconds; captured output is in `attachment-audit-v0.1/v0.3.0-rc5-tests.txt`. Both duration ablations regressed against the width-gate control, so lambda .45 / kappa 1 remain defaults. Gate 0 is proposed for simplicity because the gate-1 +0.07% L1 difference has only one trial. RC5 L2 and prospective L3/L4 validation subsequently completed; final experimental delivery is recorded below, without a 30% claim. Baseline profile evidence is now included.

## Final experimental RC5 delivery

Frozen L1–L4 validation completed; the candidate beats the uploaded source on each card but fails 30% on every card. Four-card aggregate total gain is 9.367% versus original / 2.626% versus attachment. The delivery manifest now matches the prospective freeze environment; 18 runtime hashes remain unchanged. Final 103-test checks pass under source defaults (.373s) and delivery settings (.886s). Test-only width assertions now use the configured cap, and the fake provider accepts the existing optional tiered-API tag. Initial delivery-test failures remain preserved; no runtime repair was required. Complete evidence is in `evidence/final-tests*.txt/json` and the evaluation report. Packaging/installation records are `evidence/package-validation.json` and `../pro-evaluation-v0.3.0/delivery-receipt.json`; hosted-container execution and remote upload remain unperformed. v0.4 remains unapproved/unimplemented.
