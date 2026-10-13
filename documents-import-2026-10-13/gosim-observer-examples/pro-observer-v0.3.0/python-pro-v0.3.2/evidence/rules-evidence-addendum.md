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
