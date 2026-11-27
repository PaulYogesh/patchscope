# PatchScope — offline proposal-response audit

Examines the saved *original* proposal response. No LLM calls, source-code execution, or raw source/prompt export.

| Task | Condition | Result | Proposal format | Response chars | Completion tokens / call limit |
|---|---|---|---|---:|---:|
| `mini-average-001` | bm25 | resolved | `proposal_response_not_found` | 0 | 193 / 450 |
| `mini-average-001` | native | resolved | `proposal_response_not_found` | 0 | 235 / 450 |
| `mini-average-001` | oracle | resolved | `proposal_response_not_found` | 0 | 193 / 450 |
| `mini-average-001` | placebo | resolved | `proposal_response_not_found` | 0 | 229 / 450 |
| `mini-clamp-002` | bm25 | error | `proposal_response_not_found` | 0 | 450 / 450 |
| `mini-clamp-002` | native | resolved | `proposal_response_not_found` | 0 | 302 / 450 |
| `mini-clamp-002` | oracle | error | `proposal_response_not_found` | 0 | 450 / 450 |
| `mini-clamp-002` | placebo | error | `proposal_response_not_found` | 0 | 450 / 450 |
| `mini-discount-004` | bm25 | resolved | `proposal_response_not_found` | 0 | 312 / 450 |
| `mini-discount-004` | native | resolved | `proposal_response_not_found` | 0 | 312 / 450 |
| `mini-discount-004` | oracle | resolved | `proposal_response_not_found` | 0 | 312 / 450 |
| `mini-discount-004` | placebo | resolved | `proposal_response_not_found` | 0 | 316 / 450 |
| `mini-slug-003` | bm25 | error | `proposal_response_not_found` | 0 | 450 / 450 |
| `mini-slug-003` | native | error | `proposal_response_not_found` | 0 | 450 / 450 |
| `mini-slug-003` | oracle | error | `proposal_response_not_found` | 0 | 450 / 450 |
| `mini-slug-003` | placebo | error | `proposal_response_not_found` | 0 | 450 / 450 |

`structure_valid` means the response had a three-field JSON shape. It does **not** guarantee the edit matches an observed source file. The old v0.2 `invalid_patch_proposal` error could indicate any nonconforming response, including malformed JSON. This audit cannot infer hidden reasoning or patch correctness.
