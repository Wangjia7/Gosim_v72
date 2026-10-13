# v3.5 data contract

Frozen normal-b and 180-night/6000-target long-held inputs are shared by each pair.
All episodes receive 900 normalized CPU seconds and a separate 7200 second wall
protection limit. The existing official workflow and local process_time hook are
unchanged; full input/source hashes are stored per run. Agents read public
snapshots and their own last_result, never engine truth files. D1 is unavailable.

QA facts contain requested command/prediction and returned hit IDs/scores; actual
fibre coordinates, precise raw factor and true program match are unavailable.
Facts stay immutable under resync; derived single-exposure credit is replayed and
official best_scores remain authoritative. Metrics never imply EET stacking.

Source snapshots: baseline=v3.4 final; numeric-frozen=v3.5 initial pair; agent=final
v3.5, after diagnostic replay-credit correction. Six episodes are all preserved;
final normal and long runs match delivered source. No score tuning or variance
estimation. Missing/malformed result tests and mock API regression are local.
Upload excludes inputs, truth, credentials, binaries, pyc and evidence.
