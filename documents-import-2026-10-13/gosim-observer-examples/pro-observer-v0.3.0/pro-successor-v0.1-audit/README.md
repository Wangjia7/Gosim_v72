# Pro observer audit v0.1 — approval checkpoint

2026-10-07. No successor observer has been implemented. The original Pro implementations and all 139 hash-recorded input files remain unchanged. The requested rules snapshot and audit documents are additions only.

Read [the scoped implementation plan](implementation-plan.md) and [the verified rules snapshot](rules-snapshot.md). Proposed successor: `/Users/jqwang/Documents/gosim-observer-examples/python-pro-v0.2.0`. The plan flags state/data-flow, scheduling, configuration and logging changes and gives tests, ablations and rollback for each stage.

## What was established

- Python Pro is the documented source strategy; Rust/TypeScript Pro are ports. The distribution has no Git metadata. Baseline identity is recorded by SHA-256, not an invented commit.
- The current official English guide was retrieved and matches the bundled guide after image-path normalization. All 17 engine files match their supplied manifest; the manifest's `fair-clock` label is not a commit hash.
- Original-function probes reproduce incomplete outer-fiber search, unsupported fixed fiber subsets, configured-duration violations, loss of short feasible windows, misleading required-factor reconstruction, and continued search at level 4. These prove the stated mechanisms, not whole-survey performance improvements.
- Request deadlines are discarded; per-target gain assumes individually matching programs before choosing one shared program. These are confirmed by inspection, with targeted assertions planned before implementation.
- Precise raw quality and required completion are not exposed by ordinary runtime feedback. Any evidence-based successor must represent remaining uncertainty.

## Preserved-baseline measurement

Unmodified Python Pro, public L1, model disabled, `PRO_FIXED_LEVEL=0`, 900 normalized CPU seconds. The native arm64 Python 3.9.6 interpreter was used for the accepted local CPU measurement; the platform manifest specifies Python 3.12, so a later platform-equivalent check remains necessary.

| Metric | Native baseline |
|---|---:|
| Total official-formula local score | 6236.572199 |
| Science best-contribution sum | 6037.341501 |
| Required penalty / missing | −100 / 2 |
| Timed-request reward / completed | +200 / 2 of 2 |
| Uniformity penalty | −0.769302 |
| Fault-report settlement | +100 |
| Targets observed / observe actions | 7442 / 919 |
| Decision requests | 989 |
| Agent process CPU charged by native meter | 154.376 s |
| Normalized CPU charged | 192.309 / 900 s |
| Run wall time | 166.024 s |
| Clock mode / meter | cpu / cpu |
| Termination | survey_complete |

Three baseline runs produced byte-identical `actions.jsonl` and `decisions.csv`: original Rosetta, Rosetta with an external timing wrapper, and native arm64. Actions SHA-256: `d6de526134111a1d9762b44f9e6cab4fef2fc08b1015229d9c5fdc6dd3db5240`; decisions SHA-256: `c8a3ce90124fa65a4cb49227740d63e95cb6a363f17fbb9414017f8cdf91933a`.

The first two runs exposed a local CPU-meter defect: under x86_64/Rosetta, the supplied meter records approximately 2.4% of actual CPU. Three controlled busy-loop tests reproduced this. The independently timed Rosetta baseline used 190.307649 CPU seconds inside `respond`, while its runner reported only 4.576 seconds. Do not use those runner figures to claim efficiency. The unchanged native runner avoids this host defect; no judge patch was made. The separate aggregate-CPU clamp and macOS child-process accounting limitations are documented in the rules snapshot. No runtime numerical parallelism is proposed.

## Profile and validation status

The first 20 L1 exposures were separately profiled through the unchanged observer. There were 5,490 pointing evaluations, 2,078,735 gain calls and 687,942 tangent projections. `evaluate` accounts for 56.376 of 60.773 instrumented CPU seconds; these nested cumulative times overlap. cProfile with a process-CPU timer has substantial instrumentation overhead: use the profile to locate work, not as the observer's production runtime. The full native run supplies the accepted local budget measurement.

Completed: source/rule audit, engine hash verification, deterministic bug probes, three full baseline runs, independent CPU-meter probes and a diagnostic profile. Not completed: successor implementation, successor regression suite, optimization ablations, adaptive-pacing comparisons, held-out-card evaluation, LLM QA implementation or any demonstrated score improvement. These follow the requested approval checkpoint.

## Reproduce

From this audit folder, with the original project still at the recorded location:

```bash
PROJ=/Users/jqwang/Documents/gosim-observer-examples
AUDIT=/Users/jqwang/Documents/Codex/2026-10-07/improve-the-existing-pro-observer-using/outputs/pro-successor-v0.1-audit
NATIVE_PY=/Library/Developer/CommandLineTools/usr/bin/python3

PYTHONDONTWRITEBYTECODE=1 "$NATIVE_PY" "$PROJ/runner/verify_engine.py"
PYTHONDONTWRITEBYTECODE=1 "$NATIVE_PY" "$AUDIT/regression-probes/probe.py"

mkdir -p "$AUDIT/replay-cwd"
PYTHONDONTWRITEBYTECODE=1 "$NATIVE_PY" "$PROJ/runner/run_local.py" \
  --card "$PROJ/local-cards/L1" \
  --agent '/usr/bin/env OBSERVER_MODEL_DISABLED=1 PRO_FIXED_LEVEL=0 /Library/Developer/CommandLineTools/usr/bin/python3 -B /Users/jqwang/Documents/gosim-observer-examples/python-pro/agent.py' \
  --agent-cwd "$AUDIT/replay-cwd" --wallclock 900 --out "$AUDIT/reproduced-L1"

PYTHONDONTWRITEBYTECODE=1 "$NATIVE_PY" "$AUDIT/contract-evidence/darwin_cpu_probe.py"
PYTHONDONTWRITEBYTECODE=1 /Users/jqwang/anaconda3/bin/python3 "$AUDIT/contract-evidence/darwin_cpu_probe.py"
```

The two meter probes intentionally contrast native and Rosetta interpreters. On another host use a verified native interpreter; the macOS-specific probe is not a portable Linux test. No key or model service is needed. The runner receives a clean environment; the example command pins the intended observer variables. Original agent configuration may still load its own `.env` if one is later added, so retain the recorded source/config snapshot when reproducing.

Optional diagnostic profile: `PYTHONDONTWRITEBYTECODE=1 python3 profiles/profile_baseline.py`. It intentionally stops after 20 exposures and must not be reported as a complete score comparison. Probe files emit reproduction JSON; they are audit scripts, not yet the successor's pass/fail regression suite.

## Evidence inventory and rollback

- `provenance.json`, `preservation-check.json`: input hashes and unchanged-file check.
- `baseline-effective-config.json`, `baseline-L1-public-config.json`: effective constants, model mode and public card initialization summary.
- `baseline-results/`: raw score reports, actions, decisions, observations, events, logs and clock summaries for each baseline run.
- `profiles/`: diagnostic cProfile text/data, scripts and independent CPU measurements.
- `regression-probes/`: synthetic reproduction code, outputs and exact evidence/limitations.
- `contract-evidence/`: downloaded official guide/application asset, empty normalized live/local diff, contract report and CPU-meter probes.
- `implementation-plan.md`: priority-ranked minimal changes and their impact/validation/rollback.

The original Pro folders are the rollback path. Audit-only additions can be removed independently. Implementation will use a distinct version folder after approval. Existing ZIP protocol/entrypoint and standard-library dependency policy will remain. No source was pushed and no remote competition action was taken.

Attribution: GOSIM 2026 Agentic Observer Hackathon; supplied examples/data/engine are licensed CC BY-NC 4.0 as stated in the project's LICENSE.md.
