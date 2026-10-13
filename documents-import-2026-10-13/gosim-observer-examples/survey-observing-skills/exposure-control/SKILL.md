---
name: exposure-control
description: >
  Optimize exposure duration using effective scientific return rather than
  wall-clock duration. Use it for exposure quality, completion thresholds,
  saturation, timed deadlines, visibility endpoints, split exposures, and
  event-driven duration search.
---

# Exposure Control

## Role

Choose **how long to expose** after a pointing and assignment are known or approximately known.

Optimize useful/effective progress, not nominal duration alone.

## Effective-progress model

Represent exposure as:

```text
effective_progress =
    f(duration, observing_quality, target_state, assignment, official_rules)
```

Possible quality inputs:
- seeing;
- transparency;
- sky/background;
- airmass;
- fiber offset/mis-centering;
- any GOSIM-specific quality variables.

Use only variables actually exposed by the simulator.

## DESI-derived principle

DESI's ETC uses real-time observing conditions to estimate effective signal
accumulation and stops when target depth is reached.

Transfer the principle:
- stop at useful completion;
- distinguish wall time from effective progress;
- avoid unnecessary overexposure.

Do not copy DESI exposure goals.

## Event-driven duration set

Do not search only a fixed time grid.

Construct candidates from:

1. coarse baseline grid;
2. target completion times;
3. required-satisfaction times;
4. official score-threshold crossings;
5. saturation/diminishing-return points;
6. timed-request deadline;
7. visibility-window endpoint;
8. global observing/episode endpoint;
9. other discrete scoring transitions.

Then refine only around leading candidates.

## Multi-target exposure utility

For an assignment with heterogeneous targets, evaluate:

```text
ΔU(t) = Σ_i marginal_utility_i(t)
```

This naturally captures:
- some targets finishing earlier;
- diminishing value after completion;
- overshoot;
- differences between finishing 8 targets vs partially advancing 16.

## Partial-target discipline

Consider explicit terms for:
- finish;
- continue;
- new partial;
- overshoot.

Whether these are beneficial depends on official GOSIM scoring.

## Split exposure

Only model splitting if:
- GOSIM supports it;
- quality can change within the interval;
- split actions alter score/state/feasibility;
- the expected gain justifies CPU/action overhead.

## Output contract

Return:

```text
duration_candidates
best_duration
expected_official_gain
expected_effective_progress
targets_finished
required_satisfied
timed_constraints_touched
overshoot
breakpoint_reason
cpu_cost
```
