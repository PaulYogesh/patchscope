# PatchScope v0.2.2 — Offline failure triage

## Engineering change

- Added `patchscope.failure_triage` to classify run failures by recorded stage
  and exception category. Successful test verification, failed patched tests,
  parser/patch-contract errors, tool protocol errors, and budget errors remain
  distinguishable. The triage report does not guess the model's hidden reasoning.
- Added `python -m scripts.triage_experiment --manifest experiments/pilot_v02.json`,
  which writes `.triage.md` and `.triage.json` in `reports/` from existing JSON.
- Added per-task/condition status matrix, representative errors, repeat
  trajectory counts, and observable BM25–oracle overlap checks.
- Fixed statistical reporting: **suppress McNemar p-values when pairs repeat a task**.
  The previous 0.250 p-value for native versus BM25 was based on three
  nonindependent discordances from a single task; it must not be interpreted
  as an independent-pairs hypothesis test. Paired effect sizes and task-cluster
  bootstrap summaries are retained.
- Added 6 focused regression tests. Agent behavior and the v0.2.1 recordings are unchanged.

## Why now

In `pilot-v02`, native exploration verified 9/12 episodes versus 6/12 for
BM25, oracle, and placebo. However 16/16 task/condition groups followed
identical recorded decisions across the three repetitions, and 21 runs ended
without verified repair (many with `error`, not `repair_failed_tests`).

Classify those errors **before** attributing failure to context interference or
spending compute on a larger experiment. Do not overwrite the original records.

## Run

```bash
unzip -o ~/PatchScope_v0.2.2_TRIAGE_OVERLAY.zip -d ~/patchscope
cd ~/patchscope
source .venv/bin/activate
python -m pytest -q tests/
python -m scripts.triage_experiment --manifest experiments/pilot_v02.json
cat reports/pilot-v02.triage.md
```

No new inference or trusted code execution is required.

To regenerate the descriptive report with corrected McNemar display (existing
JSON files remain untouched):

```bash
python -m scripts.report_experiment --experiment pilot-v02
```
