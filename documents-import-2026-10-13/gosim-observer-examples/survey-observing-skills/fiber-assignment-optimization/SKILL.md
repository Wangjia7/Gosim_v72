---
name: fiber-assignment-optimization
description: >
  Solve target-to-fiber allocation for a fixed pointing. Use it for exact
  reachability, collisions/conflicts, priorities, required/timed targets,
  filler use, partial-completion utility, and constrained assignment.
---

# Fiber Assignment Optimization

## Role

For a fixed pointing, determine the best legal target-to-fiber mapping.

Conceptually:

```text
U(pointing) = max over legal assignments A of Σ target_utility(i, A)
```

A pointing's value is **not** the sum of scores of nearby targets.

## Hard constraints first

Check:

- actual fiber layout and offsets;
- per-fiber reachability;
- target uniqueness;
- fiber uniqueness;
- collisions/conflicts;
- disabled/unavailable fibers if modeled;
- required calibration/fixed allocations if the task defines them;
- target state eligibility;
- timed/required eligibility.

Reject illegal assignments before scoring.

## No hard-coded fiber count

Derive:
- number of fibers;
- offsets;
- patrol/reach geometry;
- disabled fibers;
- field footprint

from the current environment or configuration.

Any literal `16` in scheduler-critical geometry must be justified by the
official current GOSIM layout.

## Assignment utility

Candidate target utility may depend on:

```text
official score gain
marginal progress
finish probability
required satisfaction
timed-request urgency
remaining future opportunities
partial/continuation value
overshoot risk
```

Keep official score terms distinct from heuristic tie-breakers.

## Filler rule

Use residual fibers only after hard/high-priority assignments are protected.

A filler should not:
- displace required/timed targets;
- consume geometry that blocks higher-value targets;
- create harmful state transitions;
- cost more CPU than its plausible score gain.

## Solver hierarchy

Under limited CPU, choose among:

1. greedy exact reachability;
2. greedy + local swaps;
3. bipartite matching;
4. min-cost flow;
5. MIP/netflow-style constrained optimization.

Use the simplest method that captures the actual constraints.

## PFS-derived lesson

PFS treats allocation as a constrained optimization distinct from field-center
selection. Preserve the same separation.

Do not copy PFS's exact non-observation costs, calibration quotas, or Cobra
geometry.

## Diagnostics

For each selected pointing, log:

```text
n_fibers
n_assigned
n_unassigned
assignment_utility
required_assigned
timed_assigned
top_unassigned_high_value_targets
reason_unassigned
conflict_count
solver_time
```

## Output contract

Return:
- legal assignment;
- assignment score/utility decomposition;
- unused fibers;
- rejected high-value targets with reasons;
- solver CPU/time;
- no target-state mutation.
