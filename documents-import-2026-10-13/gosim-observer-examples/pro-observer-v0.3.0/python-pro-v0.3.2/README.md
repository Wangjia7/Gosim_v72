# Pro observer v0.3.2 — platform manifest correction

The platform rejected v0.3.1 because its manifest included the platform-controlled `OBSERVER_MODEL_DISABLED` setting. v0.3.2 removes that setting, leaving 28 project environment settings. The previous v0.3.0 setting-count defect is also fixed. The packager checks the supported manifest fields, schema version, relative working directory, <=32 environment entries, string values, and excludes platform-owned `OBSERVER_*` settings.

Numerical observer and QA code remain byte-identical to the measured RC5 source. Only the packaging helper and manifest change. Internal decision-log version remains RC5; `VERSION` identifies this packaging revision. Previous package evidence and rejected ZIPs remain separate historical artifacts.

On the platform, select **本次不提供模型 / This evaluation without a model** to reproduce the model-disabled comparisons. The platform injects the switch; it must not be included in `observer.project.json`. With no API credentials, the observer also falls back to rules and runs without a model service. A model-enabled run may make different decisions and is not covered by the recorded no-model score comparison.

Entrypoint `python3 -u agent.py`, schema `observer-project-v1`, protocol JSONL v4, working directory `.`. The image is retained from the supplied source. No dependencies or observing policy change.

```sh
python3.12 -B -m unittest discover -s tests -v
python3.12 -B pack_agent.py --out ../python-pro-v0.3.2.zip
```

See [fix evidence](evidence/manifest-fix-v0.3.2.json), [configuration parity](evidence/manifest-parity-v0.3.2.json), [package validation](evidence/package-validation-v0.3.2.json) and [QA.md](QA.md). The previous measured results and unmet 30% performance requirement are documented in [the v0.3 evaluation report](../pro-evaluation-v0.3.0/REPORT.md). Historical benchmark commands set the platform switch only in the local runtime environment, not a submitted manifest. Native checks do not certify hosted preparation; the new ZIP must be reuploaded because the failed uploads cannot be retried.
