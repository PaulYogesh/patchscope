# PatchScope v0.3.1 — decoy-presence counterfactual

**Why:** The v0.3-alpha engineering smoke showed three wrong-locus patches in both native and explicitly misleading conditions across four tasks. An absent-decoy control is needed before making claims about why native exploration gets diverted.

## Added
- `experiments/decoy_free_native_v031.json`: the original four clean fixture repositories, matched to the 20-run v0.3 experiment on task IDs, seeds, and generation settings. Native subset = four new runs.
- `patchscope/decoy_counterfactual.py`: validates identical shared source and test bytes, exactly one additional decoy, matched experimental conditions, and matched per-run provenance before calculating paired differences.
- `scripts/compare_decoy_presence.py`: offline Markdown + JSON comparison using existing `interference-smoke-v030` native records and new clean native records.
- `tests/test_decoy_counterfactual.py`: eight focused checks for fixture parity, seeds, recovery metrics, mismatched provenance, and missing/unverified runs.

## Unchanged
The agent, intervention construction, model prompts, CLI runner, report generator, and all earlier manifests/fixtures/records. The 20-run v0.3 dataset remains a separate, immutable experimental source. No hidden chain-of-thought inference is attempted.

## Important distinctions
The new treatment is **repository decoy presence** (including tool-discovered file lists), not explicit seeded-source exposure. All reported effects are descriptive across four toy tasks. Model execution and verification still require local Ollama and explicit trusted-execution opt-in.
