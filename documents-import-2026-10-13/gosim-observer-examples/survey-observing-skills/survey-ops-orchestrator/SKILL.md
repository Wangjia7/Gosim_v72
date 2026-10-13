---
name: survey-ops-orchestrator
description: >
  Top-level controller for reviewing or optimizing a spectroscopic survey
  observer. Use it to identify which subproblem is being solved, enforce
  source precedence, separate hard feasibility from soft optimization,
  and route work to the appropriate survey-observing skill.
---

# Survey Operations Orchestrator

## Role

This is the **framework skill**, not the detailed algorithm skill.

It decides:
- what the current problem actually is;
- which rules are authoritative;
- which specialized skills are needed;
- in what order those skills should be applied;
- which changes require ablation or replay validation.

Do not put detailed geometry, deadline formulas, or optimization constants here.

## Always load first

Before making scheduler changes:

1. Inspect the current observer architecture.
2. Load `gosim26-observer-rules`.
3. Classify the issue into one or more modules:
   - pointing;
   - fiber assignment;
   - temporal scheduling;
   - exposure;
   - state;
   - CPU/search;
   - QA/retrospective.
4. Invoke only the required specialized skills.

## Source precedence

Apply this order:

1. current GOSIM docs/API/scoring;
2. explicit simulator state and hard constraints;
3. current code behavior when not contradicted by 1–2;
4. generic survey-operational principles;
5. DESI/PFS/QPlan heuristics.

Never allow a DESI/PFS heuristic to override the competition rules.

## Canonical control loop

```text
read authoritative state
→ enforce hard feasibility
→ generate candidate pointings
→ evaluate exact/approximate fiber allocation
→ construct exposure-duration candidates
→ rank feasible actions in time
→ execute
→ ingest realized outcome/quality
→ update explicit state ledger
→ perform QA/retrospective
→ repeat
```

## Hard rule

**A soft score must never compensate for a violated hard constraint.**

Examples of hard constraints:
- target/fiber unreachable;
- exposure cannot finish before a hard deadline;
- invalid API action;
- impossible observing window;
- exhausted CPU budget;
- prohibited target/state transition.

## Architectural boundaries

Keep these concepts separate:

- field/pointing generation;
- fiber allocation;
- exposure duration;
- temporal scheduling;
- state mutation;
- QA/diagnosis.

A single monolithic score function should not silently implement all six.

## Change protocol

Before a major code change, produce:

```text
Change:
Reason:
Affected module:
Interface impact:
State/reproducibility impact:
Expected score impact:
Validation:
Rollback path:
```

Prefer local fixes over framework rewrites.

## Routing rules

Use:
- `pointing-candidate-optimization` for missing fields, center offsets, search completeness.
- `fiber-assignment-optimization` for reachability, collision, filler, assignment utility.
- `queue-scheduling` for visibility, window, deadline, delay, urgency, sequencing.
- `exposure-control` for quality, completion, duration, saturation, breakpoints.
- `survey-state-ledger` for required/completed/progress inconsistencies.
- `budgeted-search` for 900-CPU allocation, caching, top-K, refinement depth.
- `observation-qa-retrospective` for logs, failure analysis, LLM explanations.

## Required output when reviewing code

Return:

1. observed architecture;
2. authoritative-rule mismatches;
3. module-by-module gaps;
4. P0/P1/P2/P3 changes;
5. CPU implications;
6. minimal implementation plan;
7. ablation/validation plan;
8. unresolved assumptions.
