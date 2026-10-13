# Normal pro fork v3.2

The package name is historical; this is a modified pro planner. Runtime input is public JSONL and own results only. Never read task cards or truth at runtime.

The root advisor.py and llm_client.py supply bounded operator_nlp and anomaly_review roles, with skills/astronomy-observer expert context. Missing keys or disabled models leave deterministic rules available. Do not call models for every numeric decision.

Keep caches scoped to one plan, preserve Python/C++ tie ordering and independent best-score/raw-factor ledgers. Register source/input hashes and switch settings in paired experiments; retain regressions. PRO_FIXED_LEVEL=0 is for controlled comparisons only.
