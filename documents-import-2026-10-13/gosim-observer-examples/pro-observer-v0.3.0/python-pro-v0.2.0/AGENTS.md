# Working on Pro v0.2.0

Read README.md, rules-snapshot.md, PROVENANCE.md and the project's supplied survey-observing skills before related changes. The original python-pro is preserved; this is the approved successor. Keep existing agent/planner/geometry/advisor responsibilities, public protocol and deterministic ties. Do not create a nine-module framework to mirror skill folders.

- `agent.py`: stdin/stdout protocol, outcome-before-resync ingestion, pacing/reserve, fault reports, structured logging integration.
- `planner.py`: public-data geometry/assignment/duration/program search, evidence bounds, request feasibility, bounded staged effort.
- `skymath.py`: public sky and square-cell geometry.
- `advisor.py`, `llm_client.py`: optional existing night/fault advisory stages, bounded retries. Missing credentials now use rules only.
- `decision_log.py`, `qa_review.py`: append-only sidecar and isolated offline/optional remote retrospective. No control authority.
- `tests/`, `benchmarks/`: synthetic regressions and isolated official-local-runner comparisons.

Never read hidden card files, weather truth or generation seeds at observer runtime. Use received initialize/state as authoritative. Do not infer required satisfaction from maximum science contribution, accumulate repeated exposure signals, or substitute real-instrument constants. Maintain null/uncertain hidden quality fields and conservative evidence bounds. Model diagnostics cannot alter numerical state or constraints.

Never print diagnostic records to protocol stdout. Keep credentials in environment, omit .env from packaging/logs/prompts and do not expose secret exception text. Offline QA needs no service; do not add per-observation blocking model calls to the observer.

All runtime configuration uses documented PRO_* or provider environment settings. Preserve feature ablations and reproduce tests before score interpretation. Distinguish correctness, implementation and measured performance; include regressions and incomplete/budget-limited runs. Use native arm64 local metering for this machine; do not patch or exploit the judge's Rosetta/parallel CPU accounting defects. Platform Python3.12 execution is not yet verified.

User approval covers scoped implementation and local comparisons. It does not authorize upload, remote evaluation, real provider calls or remote push. Preserve original files and unrelated work. Changes beyond approved architecture/interfaces/data flow require the user's stated approval protocol.
