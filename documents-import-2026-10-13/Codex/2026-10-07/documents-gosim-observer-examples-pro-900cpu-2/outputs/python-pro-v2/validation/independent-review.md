# Independent read-only review

The safe-scientific-patch workflow used a read-only Planner, the root agent as sole Implementer, and a separate read-only Reviewer.

The Reviewer independently reproduced and verified fixes for:

1. Request-only targets disappearing before deadline breakpoints were evaluated.
2. Exhausted-budget fallback selecting only the shortest exposure and an outer fibre.
3. Interrupted pointing-offset scans repeatedly restarting rather than resuming.
4. HTTP incomplete reads failing to release LLM in-flight slots.
5. A completed coarse offset scan overwriting a better existing fine estimate.

Final review independently ran all 21 regression tests successfully and found no remaining issue in these fixes. This is scoped code review and synthetic verification, not a guarantee of all-card score improvement or live model quality.

A subsequent, narrowly scoped change restored a 300-second ordinary coarse-search floor while preserving physical breakpoints and short windows. The Reviewer independently passed all 22 tests, and additionally checked 60/180-second deadlines, a 180-second setting window, and an approximately 158-second saturation point under the new floor. Full-season release results are separate.

The coarse-floor experiment was subsequently rejected based on full-season L3 regression. Final runtime behavior is restored to reviewed and benchmarked 1892ddd (comments/type annotation only differ); the additional short-request regression remains, and the final local suite passes 22/22.
