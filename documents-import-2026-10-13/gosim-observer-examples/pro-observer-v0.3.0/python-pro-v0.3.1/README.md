# Pro observer v0.3.1 — manifest compatibility fix

This packaging-only successor fixes the platform rejection `environment must be an object with at most 32 settings`. The old manifest listed 43 settings; the new one lists 29. Fourteen omitted settings equal source defaults. Numerical observer files and their internal RC5 log version remain unchanged; `VERSION` identifies this packaging revision. The packager now rejects an oversized/non-object environment and uses the current directory name for its default output ZIP.

Entrypoint is `python3 -u agent.py`, JSONL v4, `schema_version=observer-project-v1`, relative working directory `.`. The pinned image is retained. Default model-disabled operation and the measured adaptive-search overrides remain explicit. Direct Python execution reads environment variables; the platform loads the manifest. No new runtime dependency is added.

See [manifest-fix evidence](evidence/manifest-fix-v0.3.1.json), [configuration parity](evidence/manifest-parity-v0.3.1.json) and [package validation](evidence/package-validation-v0.3.1.json). The older `package-validation.json` is historical v0.3.0 evidence and missed the setting-count limit. Original score results, CPU, tests, rules, logs and optional review documentation remain in this folder and [the v0.3 evaluation report](../pro-evaluation-v0.3.0/REPORT.md). The requested 30% performance target is still unmet.

```sh
python3.12 -B -m unittest discover -s tests -v
python3.12 -B pack_agent.py --out ../python-pro-v0.3.1.zip
```

[QA.md](QA.md) documents optional offline/remote review; no service is required. [benchmarks/README.md](benchmarks/README.md) contains the historical frozen-policy reproduction overrides. Those explicit overrides are equivalent to the compact manifest in a clean environment. No new full-survey performance comparison is implied by this packaging fix. Hosted upload acceptance remains unverified until the platform prepares the new ZIP.
