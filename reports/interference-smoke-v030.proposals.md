# PatchScope — offline proposal-response audit

Examines the saved *original* proposal response. No LLM calls, source-code execution, or raw source/prompt export.

| Task | Condition | Result | Proposal format | Response chars | Completion tokens / call limit | Cap hit | Finish reason | Attempts | Rejections |
|---|---|---|---|---:|---:|---|---|---:|---|
| `mini-average-001` | bm25 | repair_failed_tests | `structure_valid` | 115 | 225 / 1400 | no | stop | 1 | — |
| `mini-average-001` | misleading | repair_failed_tests | `structure_valid` | 115 | 225 / 1400 | no | stop | 1 | — |
| `mini-average-001` | native | repair_failed_tests | `structure_valid` | 115 | 225 / 1400 | no | stop | 1 | — |
| `mini-average-001` | oracle | resolved | `structure_valid` | 115 | 534 / 1400 | no | stop | 1 | — |
| `mini-average-001` | placebo | resolved | `structure_valid` | 115 | 509 / 1400 | no | stop | 1 | — |
| `mini-clamp-002` | bm25 | resolved | `structure_valid` | 118 | 586 / 1400 | no | stop | 1 | — |
| `mini-clamp-002` | misleading | repair_failed_tests | `structure_valid` | 117 | 655 / 1400 | no | stop | 1 | — |
| `mini-clamp-002` | native | repair_failed_tests | `structure_valid` | 117 | 655 / 1400 | no | stop | 1 | — |
| `mini-clamp-002` | oracle | resolved | `structure_valid` | 118 | 586 / 1400 | no | stop | 1 | — |
| `mini-clamp-002` | placebo | resolved | `structure_valid` | 115 | 430 / 1400 | no | stop | 1 | — |
| `mini-discount-004` | bm25 | resolved | `structure_valid` | 142 | 497 / 1400 | no | stop | 1 | — |
| `mini-discount-004` | misleading | resolved | `structure_valid` | 142 | 497 / 1400 | no | stop | 1 | — |
| `mini-discount-004` | native | resolved | `structure_valid` | 142 | 258 / 1400 | no | stop | 1 | — |
| `mini-discount-004` | oracle | resolved | `structure_valid` | 142 | 258 / 1400 | no | stop | 1 | — |
| `mini-discount-004` | placebo | resolved | `structure_valid` | 147 | 274 / 1400 | no | stop | 1 | — |
| `mini-slug-003` | bm25 | error | `patch_json_invalid_or_missing` | 0 | 1400 / 1400 | yes | length | 2 | `patch_json_invalid_or_missing`, `patch_json_invalid_or_missing` |
| `mini-slug-003` | misleading | repair_failed_tests | `structure_valid` | 127 | 1205 / 1400 | no | stop | 1 | — |
| `mini-slug-003` | native | repair_failed_tests | `structure_valid` | 135 | 705 / 1400 | no | stop | 1 | — |
| `mini-slug-003` | oracle | resolved | `structure_valid` | 141 | 1070 / 1400 | no | stop | 1 | — |
| `mini-slug-003` | placebo | error | `patch_json_invalid_or_missing` | 0 | 1400 / 1400 | yes | length | 2 | `patch_json_invalid_or_missing`, `patch_json_invalid_or_missing` |

`structure_valid` means the response had a three-field JSON shape. It does **not** guarantee the edit matches an observed source file. The old v0.2 `invalid_patch_proposal` error could indicate any nonconforming response, including malformed JSON. Hitting the completion ceiling suggests possible truncation but does not prove it. Some legacy logs omit the proposal response; those are labeled `proposal_response_not_found`. This audit cannot infer hidden reasoning or patch correctness.
