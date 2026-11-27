# PatchScope v0.3.2 — content-level decoy counterfactual

- Four new neutral variants, each sharing the original task's source, issue,
  and tests with the existing clean and decoy fixtures.
- Holds the extra Python filename and file count fixed versus the decoy variant.
  The neutral module implements an unrelated, valid Python helper with a distinct
  function name; source sizes are within 10% in bytes.
- New `same_name_neutral_v032.json` manifest, same native model seeds,
  exploration/proposal budgets, task identifiers and prompt protocol.
- Offline `compare_decoy_content` produces JSON and Markdown, refusing
  incomplete, mismatched, unverified or non-parity data.
- Older experiment manifests, outcomes, and agent behavior are unchanged.
- Synthetic four-task results are engineering observations only.
