# PatchScope v0.2.4 — stage-specific completion budget diagnostic

## Why this update exists

The original four-task pilot had 21 proposal-contract errors; every failed
original proposal used the entire shared 450-completion-token allowance.
Those records cannot establish truncation because legacy transcripts did not
preserve the proposal response. In a separate v0.2.3 diagnostic, one clamp
oracle attempt became a verified repair after the optional retry, while slug
native still failed. A narrowly controlled diagnostic is preferable to an
unexplained agent overhaul.

## Engineering changes

- Optional `budgets.max_patch_completion_tokens_per_call` for proposal and
  contract-retry calls, separate from exploration's existing
  `max_completion_tokens_per_call`. Default preserves older manifests exactly.
- Per-call logs record the **requested** completion ceiling and provider
  `finish_reason` (when provided).
- Per-proposal-attempt diagnostics record completion tokens, requested cap,
  `at_completion_cap`, `finish_reason_length`, response length, and the precise
  patch-contract rejection code. A cap hit is only a *potential* truncation
  signal; it is not proof.
- The offline `audit_proposals` report shows the cap, cap-hit flag, finish
  reason, number of attempts, and rejection reasons without exporting source
  snippets or raw model responses.
- `proposal-cap-v024` is a new, isolated experiment ID. It uses the same four
  tasks, model seeds, schedule randomization, retry count, model settings, and
  all budgets from `repair-diagnostic-v023` **except** that the proposal-only
  ceiling is now 1,400 rather than 450.
- Additional regression tests cover old-manifest compatibility, strict manifest
  validation, transparent cap diagnostics, and no source modification during
  unverified simulated episodes.

## Important limitations

- Merely increasing the completion-token ceiling may not repair a task. The
  next local Qwen3.5 experiments will establish the actual outcome.
- An increase in output allowance changes cost and can change the model's
  behavior. It must be treated as an experimental protocol change rather than
  pooling v0.2.3 and v0.2.4 as if they were identical.
- Temperatures/seeds do not guarantee identical outputs. Compare full proposal
  diagnostics and action traces, not only repair success.
- No GitHub publishing has occurred. This is an implementation checkpoint.
- Pytest runs generated code on the host; a disposable folder is not isolation.
  Execute only the supplied, personally inspected toy fixtures.
