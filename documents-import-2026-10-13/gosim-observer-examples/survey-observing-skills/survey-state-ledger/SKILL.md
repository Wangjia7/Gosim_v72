---
name: survey-state-ledger
description: >
  Maintain explicit, auditable, reproducible survey state. Use it when target
  completion, required status, timed requests, score, or state correction can
  become inconsistent or when replayability is needed.
---

# Survey State Ledger

## Role

Make state transitions explicit and reproducible.

Do not reconstruct authoritative state from a downstream score when direct
state variables or events are available.

## State separation

Keep distinct concepts such as:

```text
accumulated_progress
completion_fraction
scientific_complete
score_contribution
required
required_satisfied
timed_request
deadline
quality_accepted
```

A score is an outcome, not necessarily a state variable.

## DESI MTL-derived principle

Use append-only or replayable state transitions.

Conceptual event structure:

```text
timestamp
step
entity_id
event_type
old_state
new_state
source
reason
code_version
```

Possible events:

```text
OBSERVATION_PLANNED
OBSERVATION_EXECUTED
QUALITY_ACCEPTED
QUALITY_REJECTED
TARGET_PROGRESS_UPDATED
TARGET_COMPLETED
REQUIRED_SATISFIED
TIMED_REQUEST_EXPIRED
STATE_CORRECTED
INSTRUMENT_STATE_UPDATED
```

## Authoritative-source hierarchy

When multiple state estimates exist:

1. official realized simulator state;
2. official correction/reconciliation;
3. immediate online estimate;
4. prediction made before execution.

Record the source.

## Invariants

After every update, verify:

- progress does not decrease unless official correction allows it;
- `required_satisfied` has direct evidence;
- score alone cannot toggle required state;
- completed targets do not regain remaining exposure without explicit reset;
- expired requests do not silently become feasible;
- state correction is replayable.

## State correction

Do not overwrite history silently.

Record:
- original state;
- correction source;
- corrected state;
- downstream fields invalidated;
- whether schedule replay is required.

## Reproducibility

Log:
- code version/commit;
- random seed if applicable;
- config hash;
- state snapshot/event index;
- action ID;
- result ID.

## Output contract

Provide:
- current derived state;
- event history or replay pointer;
- invariant failures;
- ambiguous state fields;
- correction recommendations.

Do not change scheduling policy here.
