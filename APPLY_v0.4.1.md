# Apply PatchScope v0.4.1 evidence-exposure audit

1. In the current `~/patchscope` working tree, extract the v0.4.1 *overlay* ZIP.
2. Run `source .venv/bin/activate && python -m pytest -q tests/`.
3. Run `python -m scripts.audit_evidence_exposure --case both`.
4. Read `reports/evidence-exposure-v041.md`.

No previous manifests or runs are overwritten and no model or fixture test
execution is invoked by the new audit command. It reads the existing twelve
original and twenty-four expanded matched records.
