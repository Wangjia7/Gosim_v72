---
name: budgeted-search
description: >
  Allocate computation under a hard CPU budget. Use it for GOSIM's fixed
  compute allowance, candidate pruning, caching, top-K exact evaluation,
  adaptive refinement, lookahead allocation, and anytime search.
---

# Budgeted Search

## Role

Treat CPU as a scarce scheduling resource.

The objective is not maximum algorithmic sophistication. It is maximum
**expected score improvement per unit compute**.

## Canonical staged search

```text
Stage 0: cache static/invariant quantities
Stage 1: hard-feasibility pruning
Stage 2: broad cheap candidate generation
Stage 3: approximate scoring
Stage 4: exact evaluation of top-K
Stage 5: event-driven exposure optimization
Stage 6: local pointing refinement
Stage 7: selective shallow lookahead
```

Not every step needs every stage.

## 900-CPU principle

If the official budget is 900 CPU units/time, explicitly track:

```text
cpu_total
cpu_used
cpu_remaining
cpu_reserved_endgame
```

Do not spend the budget uniformly over the run.

## Reserve policy

Keep reserve for:
- late required-target rescue;
- timed-request emergencies;
- final visibility windows;
- state corrections;
- endgame search when score gradients become steep.

## Caching

Cache only quantities whose dependencies are understood.

Typical cache candidates:
- static fiber geometry;
- spatial index;
- static target attributes;
- invariant score terms;
- repeated visibility calculations on a fixed grid;
- assignment subproblems with unchanged state.

Invalidate caches explicitly when dependent state changes.

## Adaptive effort

Spend more compute when:
- top candidates are close in score;
- an urgent window is closing;
- exact fiber assignment may change ranking;
- duration breakpoints are dense;
- the decision is high leverage.

Spend less when:
- one candidate dominates;
- all alternatives are infeasible;
- remaining actions are low value;
- the action is reversible and future opportunities are abundant.

## Anytime requirement

At any interruption point, the search should retain a valid best-so-far action.

Avoid algorithms that consume the remaining budget before producing any legal action.

## CPU instrumentation

Record per step:

```text
candidate_generation
visibility
fiber_assignment
exposure_search
lookahead
state_update
logging
llm
total
```

## Evaluation

Track both:
- score gain;
- CPU cost.

Useful diagnostic:

```text
marginal_search_value =
    (best_score_with_stage - best_score_without_stage)
    / extra_cpu
```

A sophisticated stage that rarely changes action should be simplified or gated.
