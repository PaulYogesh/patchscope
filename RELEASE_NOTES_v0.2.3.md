# PatchScope v0.2.3 — proposal contract diagnosis and optional recovery

## Why this release exists

The `pilot-v02` experiment returned 27 verified repairs in 48 episodes. All 21
unsuccessful runs stopped with `invalid_patch_proposal` before test verification.
The old validator merged invalid JSON and other invalid proposals into one
error. This release addresses **measurement and protocol**, not retrieval.

## Changes

- `python -m scripts.audit_proposals --manifest experiments/pilot_v02.json`
  examines the first archived proposal response in each task/condition group,
  reporting format validity, response length, and completion tokens vs limit.
  No Ollama calls, fixture execution, or raw transcript text is exported.
- Strict validator now records specific rejection codes (malformed JSON,
  missing or incorrectly typed fields, unobserved path, nonunique source fragment).
  Rejections remain failures unless a subsequent model response validates.
- One optional, explicitly budgeted contract-repair attempt, configured using
  `budgets.max_patch_retries` (default **0** for v0.2 manifests, maximum 2).
  Every attempt and its rejection reason is logged; a successful format retry
  **still requires independent pytest verification** to count as repaired.
- Proposal calls now record completion finish reasons when supplied by Ollama;
  all retries count against model-call and token budgets.
- A standalone `repair-diagnostic-v023` experiment manifest schedules four
  tasks × four conditions × one repetition, with a single repair retry.
  It has a new experiment ID and must not be pooled with `pilot-v02`.
- Reports include proposal rejections and protocol recoveries by condition.
  Prompt version and source fingerprint are updated for new records.

## Scientific caveats

- This is an engineering intervention and does **not** demonstrate improved
  context utilization. Any outcome changes may be due to the different prompt,
  retries, or model stochasticity; causal claims require controlled ablations.
- The original 48 runs remain valid historical records. Do **not** overwrite.
- The local host only uses temporary directories, not a code security sandbox.
  Execute model-edited code only on trusted included fixtures.
