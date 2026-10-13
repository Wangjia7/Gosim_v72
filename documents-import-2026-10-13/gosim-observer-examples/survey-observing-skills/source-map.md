# Source Map

This file records what each external system is used for conceptually.

## DESI survey operations

Transfer:
- closed-loop planning → selection → assignment → exposure → QA → state update;
- separation of tile/field priority from target priority;
- real-time effective exposure rather than nominal exposure alone;
- authoritative target-state and focal-plane ledgers;
- reproducibility of on-the-fly assignments;
- explicit QA before state mutation;
- pending/processed state distinction.

Do **not** transfer blindly:
- DESI-specific exposure goals;
- 5000-fiber geometry;
- dark/bright thresholds;
- moon/planet thresholds;
- exact slew or airmass coefficients.

## Subaru QPlan

Transfer:
- hard feasibility before ranking;
- explicit checks for:
  - night visibility;
  - lower/upper time limits;
  - slot duration;
  - seeing/transparency;
  - telescope limits;
  - slew/setup/teardown;
  - moon constraints;
- separate soft ranking terms such as delay, slew, program rank, and priority;
- maintain current telescope/instrument state between decisions.

Do **not** transfer blindly:
- Subaru-specific elevation/rotator limits;
- filter costs;
- fixed weights;
- actual slew model if GOSIM ignores slew.

## PFS planning tools

Transfer:
- PPP → QPlan → fiber-allocation → validation modularity;
- pointing-center optimization distinct from exact fiber allocation;
- queue/classic modes;
- proposal/target priority and accumulated effective exposure;
- fiber-hour/completion-aware utility;
- finish/continue/fill/overshoot concepts;
- constrained netflow/MIP-style assignment;
- fillers only after protecting higher-priority constraints;
- validation as a first-class stage.

Do **not** transfer blindly:
- PFS fiber counts;
- Cobra geometry;
- Gurobi-specific costs;
- calibration-fiber requirements;
- 900-second operational conventions unless GOSIM defines the same.

## DESI QuickLook

Transfer:
- online QA should be informative and loosely coupled to control;
- fast diagnostics and slow diagnostics may run on different timescales;
- warnings and alarms are distinct;
- archive metrics and applied checks;
- LLM/QA should not become the authoritative numerical scheduler.

## GOSIM

Treat as authoritative for:
- scoring;
- action/API semantics;
- target classes;
- required-target rules;
- timed-request semantics;
- exposure-quality formula;
- fiber geometry;
- CPU accounting;
- episode termination;
- any simplifications such as omitted real-world overheads.

Whenever GOSIM documentation disagrees with an astronomy reference, follow GOSIM.
