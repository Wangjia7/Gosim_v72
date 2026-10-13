# Changelog

## 2.0.0 — 2026-10-07

- Derive all fibre search indices and shared time cost from instrument layout; cover opposite field corners and polar RA queries.
- Keep independent request windows and thresholds, including short-deadline targets in initial ranking.
- Replay surviving per-exposure factor estimates on state resync; keep official score history separate.
- Include minimum legal visibility windows, legal exposure limits, saturation/threshold/window breakpoints and leading-field refinement.
- Integrate a consistent public sky quality approximation across exposure scoring, program selection and result prediction.
- Bound search by remaining CPU/wall budget; repair cost attribution, emergency model wait index, and robust fallback ordering.
- Resume pointing-offset scans across steps and validate tied offset solutions and mount reachability.
- Add per-step asynchronous LLM review, JSONL audit hook and explicit-send log review CLI.
- Enforce total retry deadline and release model slots on failed HTTP reads.
- Add synthetic regression suite and local validation report.
