# PatchScope v0.5.1 — frozen-exploration proposal control

The v0.5-alpha live policy comparison reported only 1/4 identical recorded
exploration histories across three independently generated episodes, although
policies were supposed to differ only at patch proposal time. That result
cannot cleanly isolate a proposal-context effect.

## Added

- `patchscope/frozen_replay.py`: reconstructs observed source text from a
  **single pre-existing native run** and checks it against the unchanged
  fixture; runs proposal-only off/inventory/import policy calls; logs failures,
  proposal budgets, seeds, hashes, outputs, and opt-in test verification.
- `scripts/replay_frozen_v051.py`: replay runner; supports dry-run, --task,
  --policy, and --resume; checks the model digest and saves to a NEW run ID.
- `scripts/compare_frozen_v051.py`: refuses incomplete or provenance-mismatched
  three-arm comparisons and generates a separate Markdown/JSON report.
- `tests/test_frozen_replay.py`: unit tests for source/replay integrity,
  proposal policy isolation, and comparison rejection paths.

## Experimental guardrails

- No alteration to old agent, tasks, or manifests.
- A replay can edit only previously observed source code; no oracle file or
  test source is added to the model's observed evidence.
- Proposal-only token usage is never represented as full-agent token usage.
- This is a protocol-validity control, not a claimed mitigation or a new
  scientific positive finding.
