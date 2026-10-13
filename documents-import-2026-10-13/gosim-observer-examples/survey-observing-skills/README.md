# Survey Observing Skills Framework

A modular skill hierarchy for developing, reviewing, and optimizing a GOSIM-style spectroscopic survey observer.

## Design principle

Keep three layers separate:

1. **Authoritative task rules** — what the simulator/competition actually allows and scores.
2. **Operational architecture** — how a robust survey should be organized.
3. **Optimization modules** — how to solve pointing, fiber, timing, exposure, state, CPU, and QA subproblems.

Source-precedence rule:

> **GOSIM rules > hard physical/API constraints > generic survey-operation principles > DESI/PFS/QPlan heuristics**

Never copy instrument-specific constants from DESI, PFS, or Subaru QPlan unless the current task explicitly uses the same definition.

## Skill tree

```text
survey-ops-orchestrator
        │
        ├── ALWAYS → gosim26-observer-rules
        │
        ├── pointing problem → pointing-candidate-optimization
        │                       └── fiber-assignment-optimization
        │
        ├── timing problem → queue-scheduling
        │
        ├── exposure problem → exposure-control
        │
        ├── state problem → survey-state-ledger
        │
        ├── CPU/performance problem → budgeted-search
        │
        └── logs/diagnostics → observation-qa-retrospective
```

## Global execution order

Unless the competition rules require otherwise:

```text
authoritative rules/state
    ↓
hard feasibility
    ↓
candidate pointings
    ↓
fiber assignment
    ↓
exposure-duration optimization
    ↓
temporal/opportunity-cost ranking
    ↓
execute
    ↓
quality assessment
    ↓
state-ledger update
    ↓
retrospective / replanning
```

## Global code-change policy

When modifying an existing observer:

- read the baseline first;
- create a new version instead of overwriting the baseline;
- preserve data flow, function organization, interfaces, variable naming, randomness, and output formats when possible;
- before any unavoidable structural/interface change, list:
  - what changes;
  - why it is required;
  - which behavior may change;
  - reproducibility implications;
- validate major changes by identical-input/identical-seed replay;
- prefer incremental ablations over enabling all heuristics at once.

## Recommended ablation sequence

```text
baseline
→ authoritative-rule audit
→ fiber geometry
→ candidate completion
→ deadline/window feasibility
→ required-state correction
→ event-driven exposure optimization
→ CPU-staged search
→ structured decision logs
→ optional LLM retrospective
```

## Skills

- `survey-ops-orchestrator/`: top-level controller and routing logic.
- `gosim26-observer-rules/`: authoritative competition/API/scoring adapter.
- `pointing-candidate-optimization/`: field-center generation and local refinement.
- `fiber-assignment-optimization/`: exact reachability and constrained fiber utility.
- `queue-scheduling/`: time windows, visibility, delay, urgency, opportunity cost.
- `exposure-control/`: effective exposure and event-driven duration search.
- `survey-state-ledger/`: explicit target/instrument state and reproducible history.
- `budgeted-search/`: computation allocation under a fixed CPU budget.
- `observation-qa-retrospective/`: deterministic QA plus optional LLM diagnosis.

See `source-map.md` for the intended mapping to DESI, Subaru QPlan, PFS planning tools, and GOSIM.
