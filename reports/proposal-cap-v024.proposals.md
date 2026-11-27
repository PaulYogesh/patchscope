# PatchScope — offline proposal-response audit

Examines the saved *original* proposal response. No LLM calls, source-code execution, or raw source/prompt export.

| Task | Condition | Result | Proposal format | Response chars | Completion tokens / call limit | Cap hit | Finish reason | Attempts | Rejections |
|---|---|---|---|---:|---:|---|---|---:|---|
| `mini-clamp-002` | oracle | resolved | `structure_valid` | 115 | 316 / 1400 | no | stop | 1 | — |
| `mini-slug-003` | native | resolved | `structure_valid` | 337 | 989 / 1400 | no | stop | 1 | — |

`structure_valid` means the response had a three-field JSON shape. It does **not** guarantee the edit matches an observed source file. The old v0.2 `invalid_patch_proposal` error could indicate any nonconforming response, including malformed JSON. Hitting the completion ceiling suggests possible truncation but does not prove it. Some legacy logs omit the proposal response; those are labeled `proposal_response_not_found`. This audit cannot infer hidden reasoning or patch correctness.
