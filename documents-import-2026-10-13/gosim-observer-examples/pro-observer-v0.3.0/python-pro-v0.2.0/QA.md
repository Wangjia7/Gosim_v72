# Structured decisions and retrospective QA

`DecisionLogger(config, path=None).emit(record)` appends JSONL to `PRO_LOG_PATH`, default `decision-log.jsonl`. Every emit adds schema `pro-decision-log-v1`, successor version, sanitized config hash and sequential event ID. Root agent supplies step/action correlation, public state identifiers, predictions, constraints, alternatives, outcome transitions and timing. The helper never writes protocol stdout. An unavailable log path falls back to structured stderr. Credentials are removed by field names and matching environment-secret values; URLs drop credentials/query strings. Nonfinite numbers become null. Never supply hidden card truth or credentials to the logger. Unknown realized raw quality/required truth stays null or explicitly uncertain.

Offline whole-log retrospective:

```
python3 qa_review.py run decision-log.jsonl
```

Individual decision/outcome replay:

```
python3 qa_review.py step decision-log.jsonl --step 12
```

The CLI has no numerical scheduler or state-mutation reference. It reads evidence and outputs diagnostics only. Run mode retains the latest 1000 records in a bounded queue; use step mode to examine earlier decisions. A record above 512 KiB is rejected. Deterministic checks flag explicitly infeasible actions, exhausted CPU and missing outcomes, never infer unprovided geometry or hidden quality. The observer never blocks on retrospective review. Run this CLI after a run or as a separate event-triggered consumer once an outcome is appended; repeated invocations should be managed externally with at most one consumer in flight. No automatic remote calls or service required.

Optional remote diagnostic call requires `--remote` and all three environment variables `PRO_REVIEW_BASE_URL` (OpenAI-compatible endpoint), `PRO_REVIEW_MODEL`, `PRO_REVIEW_API_KEY`. Credentials are never included in prompts or persisted output. Example:

```
python3 qa_review.py step decision-log.jsonl --step 12 --remote --timeout 15 --retries 1
```

No default provider/model or credential inheritance. Timeout is a total elapsed call budget (maximum 60 seconds); retries capped at 2, response/request limit of 512 KiB, one in-flight request. A daemon worker allows the caller to return at the total deadline even if a provider ignores its socket timeout; the abandoned request cannot alter observer state. The standalone CLI exits after review. An unavailable/malformed/oversized/nonfinite response returns a bounded error category and leaves deterministic diagnostics usable. Provider replies must contain exactly `warnings`, `alarms`, `hypotheses`, `evidence`, `recommended_ablations` (bounded string arrays), and finite `confidence` in [0,1]. Reviews are proposals for separate experiments, never authoritative scores or commands. Model latency is recorded separately; token cost is unavailable unless measured outside this interface.

Tests use fake providers only:

```
python3 -m unittest discover -s tests -p test_qa.py
```

To review **every step** with bounded streaming memory, use paired replay:

```
python3 qa_review.py replay decision-log.jsonl > reviews.jsonl
```

Replay emits one diagnostic JSON line for each adjacent decision/outcome pair, including missing or pending outcomes. `--remote` explicitly enables a provider call per replayed packet; it is off by default and never called by the observer. A timed-out request still alive blocks later requests on that client (`in_flight_limit`), preventing a growing worker queue. Observing choices remain unchanged by review output. Legal wait actions do not trigger observing-feasibility alarms. Provider-supplied nonnegative integer token usage is retained when available; monetary cost is null, never estimated without pricing evidence.

Remote whole-log context is byte-bounded separately from the1000-record offline queue. The reviewer receives recent whole records that fit the512KiB serialized request, preceded by `coverage` reporting records received/included/omitted, skipped oversized records and whether only a recent window is present. These counts describe input supplied to the client; the run loader may already have retained only1000 recent records. Successful remote output repeats coverage, so it cannot be mistaken for exhaustive whole-run analysis. Small individual decision/outcome packets remain complete. An individually oversized record is skipped when other records fit; if no record fits, the client returns `request_too_large` without contacting the service. Credential redaction happens before context selection. No actual provider calls are made by tests.
