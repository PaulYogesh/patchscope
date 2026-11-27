# PatchScope v0.4.1 — Offline evidence-exposure audit

This additive update contains an audit only; it does not change the coding
agent, generator settings, manifests, fixtures, verification protocol or prior
run records.

## Why

The original four decoy tasks caused three wrong-locus edits; eight new benchmark
tasks produced no wrong-locus edits. These are two different sets of curated
tasks, not a single randomized sample. The new benchmark's `service.py` modules
explicitly import the correct implementation, while the `_compat.py` decoys
are not statically imported by the agent-visible source modules. This is one
plausible reason the expanded tasks were more resilient, not an established
mechanism.

## Usage

```sh
cd ~/patchscope
source .venv/bin/activate
python -m pytest -q tests/
python -m scripts.audit_evidence_exposure --case both
cat reports/evidence-exposure-v041.md
```

The offline audit compares the original and expanded clean/neutral/decoy
records. It checks complete matched episodes using the existing comparison
contract, records observed files and valid read actions, records the first read,
and lists basic static source importers of the oracle and decoy modules.

This is a *diagnostic*, not a mitigation. Static imports are incomplete proxies
for actual Python runtime behavior; observed code is not a measure of model
attention or hidden reasoning. No new model calls or execution of model-generated
code is performed by the audit.

## Repository hygiene

Some prior v0.4 source ZIPs included generated `.pytest_cache` and `__pycache__`
directories under a benchmark fixture. Such generated artifacts should be
excluded from the public release. The original fixture source and run records
should be kept intact for research provenance.
