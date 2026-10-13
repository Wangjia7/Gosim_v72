---
name: pointing-candidate-optimization
description: >
  Generate and refine candidate telescope pointings for a multi-fiber survey.
  Use it for field-center completeness, pointing offsets, density/utility
  seeding, urgent-target anchors, and local refinement before exact fiber
  assignment.
---

# Pointing Candidate Optimization

## Role

Choose **where the telescope could point**.

Do not confuse:
- targets near a field center;
- targets actually reachable by fibers;
- targets selected by the final fiber assignment.

This skill produces candidate centers. Exact assignment belongs to
`fiber-assignment-optimization`.

## Inputs

- current target state;
- current time;
- instrument/fiber footprint;
- required/timed targets;
- approximate per-target utility;
- CPU budget available for candidate generation.

## Candidate sources

Generate candidates from a union of:

1. urgent/deadline anchors;
2. required-target anchors;
3. high-value target anchors;
4. density/KDE/cluster seeds;
5. partially completed/continuation-rich regions;
6. local offsets around leading centers;
7. optional geometry-induced centers that improve multi-target reachability.

Do not rely on one density heuristic.

## Full-footprint search rule

Never use a center-neighborhood radius that is smaller than the full fiber footprint.

At minimum:

```text
R_query >= max_i ||fiber_offset_i|| + matching_tolerance
```

Then pass candidates to exact fiber reachability.

If the layout is not radially symmetric, prefer a conservative bounding
region followed by exact geometry tests.

## Utility approximation

A cheap pointing proxy may include:

```text
approx_utility =
    expected useful progress
  + finish bonus
  + continue bonus
  + required/timed urgency
  + fill potential
  - overshoot
  - predicted conflicts
```

But the final score of a promising center should use actual/near-actual
fiber assignment.

## PFS-inspired principles

Prefer pointings that:
- yield useful fiber-hours/progress;
- finish already-near-complete targets;
- continue partially completed targets when strategically useful;
- fill otherwise idle fibers;
- avoid excessive overshoot;
- avoid opening too many low-value partial targets.

Treat these as heuristics, not fixed PFS coefficients.

## Search structure under CPU pressure

```text
broad cheap seeds
→ deduplicate nearby centers
→ cheap approximate utility
→ top-K
→ exact fiber allocation
→ local center refinement
→ retain Pareto-competitive candidates
```

## Candidate completeness tests

Create synthetic/replay cases where:
- only a diagonal/outer fiber can reach a valuable target;
- a small center shift captures multiple high-value targets;
- a required target lies in a sparse field;
- a timed target is absent from density-driven seeds;
- two centers have similar density but very different feasible assignments.

## Output contract

Return candidates with:

```text
center
origin/reason
approx_utility
urgent_targets_covered
required_targets_covered
estimated_fill
geometry_bounds
refinement_parent
```

Do not mutate target state.
