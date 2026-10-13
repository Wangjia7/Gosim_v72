# python-pro-900cpu

This directory is a derived, versioned implementation based on
`/Users/jqwang/Documents/gosim-observer-examples/python-pro`.

- Baseline: `python-pro` participant-agent-protocol-v4 example.
- Variant: adaptive field candidates, deadline-safe exposure planning, conservative
  state resynchronisation, and asynchronous LLM log/step review.
- The baseline source is not modified.

The implementation keeps the protocol and JSONL output contract unchanged. LLM
reviews are advisory only; rule-based planning remains the fallback when the
model is unavailable or returns invalid data.
