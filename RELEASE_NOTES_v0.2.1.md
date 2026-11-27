# PatchScope v0.2.1 — Instrumentation reliability and trajectory audit

This update **does not require rerunning previous experiments** and does not push anything to GitHub.

## Why

The 8-run `smoke-v02` experiment completed with 8/8 verified repairs. It establishes
an end-to-end execution baseline, but an all-success single-task smoke does not
measure a retrieval advantage. Equal per-condition token totals in repetitions
make inspection of repeated *actions* useful before claiming replication.

## New

- `python -m scripts.audit_experiment --manifest experiments/smoke_v02.json`
  creates `reports/smoke-v02.audit.md` and `.audit.json` without inference.
- Per-condition ground-truth-file exposure, off-target file reads, repeated
  reads, and whether a seeded excerpt was expanded by a read call.
- Stable signatures of observable tool decisions and patch proposals, with
  diagnostic flags when repeated runs take exactly the same recorded path.
- A partially seeded file can now be expanded by the agent's read tool instead
  of automatically being classified as already read.
- `source_tree_sha256` and `git_worktree_dirty` provenance in **future** run
  records and reports. This remedies misleading Git HEAD identifiers when
  working from ZIP overlays before committing the new code.
- Eight new unit and CLI tests; no modification to existing fixture issues or
  sample manifests.

## Apply (Ubuntu)

```bash
cd ~/patchscope
unzip -o ~/PatchScope_v0.2.1_AUDIT_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
python -m scripts.audit_experiment --manifest experiments/smoke_v02.json
cat reports/smoke-v02.audit.md
```

`runs/` is ignored by Git; keep existing JSON records. Do not rerun with
`--force` because the protocol/code fingerprint changed after the smoke.

The original 8 runs can be analyzed retrospectively; new provenance fields
only appear on runs executed after installing this update.

**Verification note:** local tests were run with a test-only stand-in for the
not-installed `rank_bm25` package in this sandbox. The stand-in is NOT included
in any release ZIP. Please confirm the full test suite on your Ubuntu machine
using your actual pinned dependencies before making scientific claims.

**Experimental note:** the `pilot_v02.json` 48-run engineering pilot still uses
only four toy tasks. Its results should not be presented as evidence of
performance advantages in real-world software repair.
