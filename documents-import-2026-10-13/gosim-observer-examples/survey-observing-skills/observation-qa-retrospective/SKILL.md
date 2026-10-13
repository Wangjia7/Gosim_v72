---
name: observation-qa-retrospective
description: >
  Perform deterministic observation QA and optional LLM-assisted retrospective
  analysis. Use it for structured logs, warning/alarm detection, predicted-vs-
  realized comparison, recurring failure diagnosis, and strategy suggestions.
---

# Observation QA and Retrospective

## Role

Inspect what happened after each action and identify whether the scheduler,
instrument model, state update, or heuristic behaved unexpectedly.

The LLM is an analyst, not an authoritative numerical controller.

## DESI QuickLook-derived principle

Keep QA loosely coupled to control.

If the LLM/QA layer is unavailable:
- deterministic scheduling should still run;
- state correctness should not depend on the LLM;
- geometry/deadline/score arithmetic must remain deterministic.

## Two QA layers

### Deterministic QA

Check:
- action legality;
- assignment legality;
- expected vs realized exposure quality;
- expected vs realized score gain;
- required/timed transitions;
- state invariants;
- CPU budget;
- missing/unused fibers;
- deadline/window compliance.

### LLM retrospective

Use structured data to ask:
- Why did candidate A beat B?
- Was an urgent target omitted?
- Was candidate generation incomplete?
- Did duration miss a breakpoint?
- Why did predicted gain exceed realized gain?
- Was CPU spent on a decision that was obvious?
- Is the same failure recurring?
- Which heuristic should be tested by ablation?

## Warning vs alarm

Adopt two levels:

**Warning**
- suspicious but still scientifically/competitively usable;
- mild prediction error;
- slightly inefficient exposure;
- unusual but legal assignment.

**Alarm**
- hard constraint violated;
- required state corrupted;
- timed request missed despite feasible opportunity;
- impossible fiber assignment accepted;
- CPU budget danger;
- score/state inconsistency.

## Structured decision packet

Recommended schema:

```json
{
  "step": 0,
  "time": null,
  "version": null,
  "state_id": null,
  "selected": {
    "pointing": null,
    "duration": null,
    "predicted_gain": null
  },
  "assignment": {
    "n_assigned": 0,
    "required": [],
    "timed": [],
    "unused_fibers": []
  },
  "realized": {
    "gain": null,
    "quality": null,
    "state_changes": []
  },
  "constraints": {
    "visibility_end": null,
    "nearest_deadline": null,
    "cpu_remaining": null
  },
  "alternatives": [],
  "cpu": {}
}
```

Adapt to the existing codebase instead of forcing a rewrite.

## LLM safety boundary

LLM may:
- summarize;
- explain;
- diagnose;
- cluster failure modes;
- propose offline experiments.

LLM must not silently:
- change target completion;
- set required state;
- calculate authoritative fiber reachability;
- decide deadline feasibility;
- overwrite official score;
- mutate scheduler state.

## Retrospective output

Return:

```text
warnings
alarms
root-cause hypotheses
evidence
top rejected alternative analysis
predicted-vs-realized delta
repeated-pattern flags
recommended ablation
confidence/uncertainty
```
