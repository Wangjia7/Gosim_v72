---
name: queue-scheduling
description: >
  Schedule feasible observations in time. Use it for visibility windows,
  lower/upper time limits, timed-request deadlines, delay, slew/overhead when
  modeled, urgency, future opportunity cost, sequencing, and queue ranking.
---

# Queue Scheduling

## Role

Choose **when** to execute a feasible pointing/assignment/exposure option.

This skill separates:

```text
hard temporal feasibility
from
soft temporal ranking
```

## Hard feasibility

An action is feasible only if the full action interval fits the available window.

Generic form:

```text
setup
+ delay
+ slew/transition if modeled
+ exposure
+ teardown if modeled
<= allowed time interval
```

For a hard request deadline:

```text
exposure_end <= request_deadline
```

unless official GOSIM rules explicitly define another condition.

Checking only `start_time < deadline` is insufficient.

## QPlan-derived checks

When relevant to the simulator, evaluate:

- slot duration;
- lower time limit;
- upper time limit;
- night visibility;
- environmental constraints;
- telescope/instrument limits;
- delay until visibility;
- transition/slew;
- moon/other avoidance;
- setup/teardown.

Only model terms actually represented by GOSIM.

## Remaining-window state

For each candidate compute:

```text
window_start
window_end
deadline
remaining_required_exposure
slack = limiting_end - now - remaining_required_exposure
```

Use slack as an urgency feature.

## Opportunity cost

Distinguish:

- visible now and visible many times later;
- visible now and entering final feasible opportunity;
- high score but flexible timing;
- moderate score but expiring soon.

A useful soft ranking may include:

```text
expected_gain
+ deadline_urgency
+ required_urgency
+ scarcity_of_future_opportunities
+ continuation_value
- transition_cost
- delay_cost
- future_blocking_cost
```

Hard feasibility still dominates all terms.

## Lookahead

If CPU permits, prefer shallow targeted lookahead over uniform deep search.

Examples:
- compare "observe urgent target now" vs "postpone one step";
- estimate next-best action after each top-K candidate;
- reserve lookahead for tight windows and endgame.

## Output contract

For each candidate action return:

```text
feasible
earliest_start
latest_finish
slack
urgency_terms
transition_cost
future_opportunity_estimate
temporal_score
rejection_reason
```

Do not decide fiber geometry here.
