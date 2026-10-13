# Closed-loop telescope observer

initialize → public catalog, scoring and fibre geometry → planner initialization

Each decision processes the previous observation, then state resync, current
bulletins and active requests. Public maximum score and raw factor bounds remain
separate. Revoked observe indexes are replayed, and a superseded model response is
invalidated by the updated ledger version.

`opportunities.py` intersects continuous altitude windows with night intervals.
`planner.py` estimates flux-dependent single-exposure value, required opportunity
loss and each request's distinct deadline/threshold. Cached physical predictions
are shared across programs. One exposure uses exactly one program; selection
compares all duration/program choices jointly instead of voting after assigning.

`joint.cpp` classifies targets in the gnomonic Alt-Az grid and chooses the best
positive gain per fibre for each exposure choice. `native.py` returns only the
best field choice to avoid materializing every losing assignment in Python. The
fallback performs the same comparison in cached Python. C++ process CPU counts
in the same process; the field loop checks its CPU deadline after an incumbent
exists. Active requests are explicitly admitted outside the global proxy top-k and sorted by last legal start. Miss edge margins are bounded within each cell; new requests cannot be permanently vetoed by old misses. Completion rewards ramp above their threshold under quality uncertainty. The broader candidate search is approximate, not an optimality proof.

`geometry_feedback.py` separates hit/miss evidence from throughput scores. A
numerical offset proposal must explain independent future exposures; evidence is
bounded, and contradictions can restore the previous offset. LLM output cannot
supply offset angles. The 0.20 degree component bound is a tested hypothesis range,
not an official hard limit or a guarantee of diagnosis.

`advisor.py` loads the bundled astronomy expert skill into both LLM roles. The
operator role compiles source-cited IDs/classes/preferences, which expire and have
only a small ranking effect. The anomaly role reviews cumulative hourly E/scale,
geometry evidence, earthquake/weather explanations and data-loss state. Paid
report recommendations must pass the existing numeric fault gate and report cost
logic; model diagnosis does not replace that gate.

`operator_cli.py` is a side adapter because official v4 supplies request reasons
but no dedicated human chat channel. Optional operator_messages are an internal
integration field; they never appear in decision_response. Model content cannot
change catalogue positions, request rewards or the public score contract.

`agent.py` keeps JSONL protocol fields at the response root, one reply per request,
logs to stderr, and measures CPU/wall costs separately. `build_native.py` compiles
on the deployment host, and `pack_agent.py` excludes binaries, credentials and
non-production data. The run command is a one-dimensional argv array.

DESI informs the architecture, not hardcoded challenge thresholds. References:
https://fiberassign.readthedocs.io/en/latest/overview.html ;
https://arxiv.org/abs/2306.06309 ; attached QLReqs_v1.0.docx and surveyops.pdf.
The QuickLook attachment is historical requirements data, not an instruction to
install DESI pipelines or invent CCD/FVC measurements unavailable to this agent.
