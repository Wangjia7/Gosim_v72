# Correctness checks

Run from the successor folder:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The suite uses the standard library, synthetic public-state fixtures and the supplied official engine. `test_contract.py` uses `GOSIM_EXAMPLES_ROOT` (default `~/Documents/gosim-observer-examples`) to locate the original examples folder for test-time comparisons; the observer never imports the engine or opens a task card. Tests fake provider responses and never call a real model.

| Area | Regression coverage |
|---|---|
| Pointing/fibers | Outer and diagonal footprint, center shifts, RA wrap/poles, gaps, 2/3/4/6-square layouts, unique legal assignments |
| Timing | Full request interval, inclusive equality and ±1 second, overlapping requests, whole-interval altitude, 100-second visibility/request windows with event refinement on/off |
| Exposure | Loaded min/max at every search level, clipped night/episode minimum, model breakpoints and saturation, assignment changes with duration, capped event work |
| State | Maximum-score repeats, distinct maximum factor, rounded feedback bounds, ambiguous/zero mismatch multiplier, authoritative correction, index invalidation, deduplication and cache invalidation |
| CPU | Zero budget, stage deadlines, best-so-far interruption, legal wait/finish, selected-level attribution |
| Logs/QA | Decision/outcome correlation, pending feedback, numeric values and nulls, credential redaction, malformed/unavailable provider, invalid endpoint, bounded retry/timeout and replay |

These assertions establish local correctness for their fixtures. They do not prove hidden quality predictions or hidden-card performance. Final RC5 validation uses native arm64 Python 3.12.14. All 103 tests passed under source defaults (.373s) and the exact delivery manifest environment (.886s); outputs are in `../evidence/final-tests-source-defaults.txt`, `final-tests-delivery-manifest.txt`, and `final-tests.json`. Test-only compatibility changes use the configured search-width bound and accept the existing optional provider tag; initial first-pass failures remain preserved. No actual model API calls were made. These results do not validate the hosted container or imply the unmet 30% score goal.
