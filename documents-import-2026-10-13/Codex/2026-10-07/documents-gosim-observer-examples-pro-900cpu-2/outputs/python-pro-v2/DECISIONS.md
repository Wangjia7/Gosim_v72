# v2 design decisions — 2026-10-07

1. Source: python-pro. The supplied directory has no Git history; preserve file hashes and an independent local baseline. Do not overwrite upstream or modify the scoring engine.
2. Protocol, public score definitions and RNG stay unchanged. The participant never reads card files. Test runners may access the supplied public practice cards.
3. A request window gates its own bonus, not all ordinary science for that target. Overlapping requests retain distinct thresholds and deadlines.
4. The official best score and the largest surviving estimated exposure factor are separate state. A resync first ingests the pending result, then invalidates history by observe_index. Unknown history never proves required completion. Scores alone do not identify true factors when program matching is hidden.
5. Whole-field candidate coverage is a conservative anchor-centred spherical cap plus refinement allowance, followed by exact fibre classification. Anchor selection itself remains heuristic.
6. The exposure model integrates a quadratic through public sky samples at exposure horizon start/mid/end. It is a bounded approximation, not a forecast of unannounced weather. Leading fields receive integer-neighbour breakpoint and duration refinement; no claim of a global optimum.
7. Offset scans freeze their evidence and retain a cursor across turns. A finished coarse scan can be used even when fine search cannot finish. Never publish partial scores. Search budgets are cooperative, so a single geometry/target evaluation may slightly exceed its slice.
8. Every step invokes the review hook. Network review is asynchronous, bounded, advisory, and may batch or skip steps under backpressure. Responses cannot mutate state or bypass deadlines; local JSONL can preserve every step. This explicitly supersedes upstream AGENTS.md's prohibition on per-decision model calls, as requested by the user.
9. No actual external LLM calls are made during validation. Transport/schema/timeouts are tested with local fakes. Live provider latency and review quality remain unverified.
10. Native /usr/bin/python3 is used for final local benchmark timing after the Conda runtime's local meter failed a process_time cross-check. The upstream runner is untouched. Early Conda scores are exploratory, not CPU-budget evidence.

11. An ordinary 300-second coarse-search floor was tested as commit c006296 to reduce short filler exposures. It reduced decision count but regressed L3 by 6.36% and missed one request; it was rejected. Restore the already tested behavior of 1892ddd, retaining real short-exposure candidates and all correctness fixes. Keep both experiments in validation. These results do not establish a generally higher-scoring strategy.
