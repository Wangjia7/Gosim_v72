---
name: gosim26-observer-rules
description: >
  Authoritative adapter for the GOSIM Survey26 observer task. Use it before
  applying any DESI, PFS, Subaru QPlan, or generic astronomy heuristic.
  It records official scoring, action semantics, hard constraints, CPU budget,
  target-state rules, timed requests, and simulator simplifications.
---

# GOSIM26 Observer Rules

## Status

This skill is the **authoritative adapter layer**.

It should be updated whenever the official GOSIM documentation, scoring rules,
API, or competition runtime changes.

Do not infer missing competition rules from DESI/PFS behavior.

## Required rule inventory

Before optimization, extract and record the current official values/semantics for:

- total score formula;
- best-score/science-score contribution;
- required-target penalties;
- timed-request rewards/penalties;
- uniformity penalties;
- report/result-submission scoring;
- observation action schema;
- fiber layout and offsets;
- exposure-quality model;
- target completion rule;
- partial-exposure behavior;
- timed-request start/end semantics;
- required-target completion semantics;
- state-correction semantics;
- weather/quality observables;
- total observing duration;
- CPU budget and how it is measured;
- action limits;
- episode termination;
- scoring latency or delayed feedback.

## Rule precedence

When there is a conflict:

```text
official docs/runtime
> official examples/reference implementation
> current baseline code
> astronomy best practice
```

## Competition-vs-reality filter

For every proposed real-world improvement, ask:

1. Does GOSIM actually model this effect?
2. Does it affect score?
3. Does it consume CPU?
4. Can the action API exploit it?
5. Is it a hard rule or merely a plausible physical effect?

If any answer is "no", do not spend large CPU budget on it without evidence.

## Known audit targets

Explicitly check the current observer for:

- hard-coded 16-fiber assumptions;
- incomplete candidate search footprint;
- timed requests whose exposure can extend past deadline;
- required-state inference from score;
- fixed duration grids missing event breakpoints;
- unnecessary real-world overhead optimization if the simulator omits it;
- CPU usage that does not improve official score.

## State schema recommendation

Keep competition state explicit:

```text
target_id
target_class
score_parameters
progress
completion_fraction
scientific_complete
required
required_satisfied
timed_request
request_start
request_deadline
visibility_window
last_observed
last_quality
```

Only include fields supported or derivable from official state.

## Validation

Every change should be evaluated against official metrics, not surrogate astronomy metrics.

Minimum comparison:

```text
total score
science/best score
required misses
timed-request score
uniformity penalty
number of targets observed
effective completion
CPU used
```

## TODO for implementation

When installing this skill for a specific competition snapshot, add a
`rules-snapshot.md` generated from the current official docs and include:
- retrieval date;
- docs version if available;
- exact definitions;
- unresolved ambiguities;
- links or citations.
