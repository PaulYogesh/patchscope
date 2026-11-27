# PatchScope failure triage — pilot-v02

This diagnostic reads existing JSON records only. It does **not** rerun the model, execute fixture code, or reveal hidden reasoning.

## Effective diversity

- Recorded runs: **48**
- Distinct tasks: **4**
- Distinct task–condition trajectory signatures: **16**
- Identical-repetition groups: **16 / 16**

Repeated identical trajectories do not provide independent behavioral variation. Do not interpret these run counts as an effective sample of independent tasks.

## Outcomes by task and context

| Task | native | bm25 | placebo | oracle |
|---|---:|---:|---:|---:|
| `mini-average-001` | 3/3 (resolved×3) | 3/3 (resolved×3) | 3/3 (resolved×3) | 3/3 (resolved×3) |
| `mini-clamp-002` | 3/3 (resolved×3) | 0/3 (error×3) | 0/3 (error×3) | 0/3 (error×3) |
| `mini-discount-004` | 3/3 (resolved×3) | 3/3 (resolved×3) | 3/3 (resolved×3) | 3/3 (resolved×3) |
| `mini-slug-003` | 0/3 (error×3) | 0/3 (error×3) | 0/3 (error×3) | 0/3 (error×3) |

## Failure breakdown

| Condition | Recorded runs | Verified | Failure categories |
|---|---:|---:|---|
| bm25 | 12 | 6 | `patch_contract_validation` 6 |
| native | 12 | 9 | `patch_contract_validation` 3 |
| oracle | 12 | 6 | `patch_contract_validation` 6 |
| placebo | 12 | 6 | `patch_contract_validation` 6 |

## Representative unsuccessful records

One example per distinct task/condition/failure signature. Error strings are shortened; no source transcripts are included.

| Example run | Similar repetitions | Observed stopping stage | Category | Error |
|---|---:|---|---|---|
| `mini-clamp-002__bm25__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |
| `mini-clamp-002__placebo__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |
| `mini-clamp-002__oracle__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |
| `mini-slug-003__native__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |
| `mini-slug-003__bm25__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |
| `mini-slug-003__placebo__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |
| `mini-slug-003__oracle__r00` | 3 | proposal_parsing_or_validation | `patch_contract_validation` | ValueError: invalid_patch_proposal |

## BM25–oracle diagnostic overlap

12/12 matched task–repetition pairs had identical seeded paths, displayed character counts, recorded action signatures, and total tokens. This is evidence of observationally overlapping interventions, **not** proof that every prompt byte was identical.

## Next interpretation rule

A run marked `error` is **not** automatically a demonstrated incorrect code repair. Classify its recorded exception and stopping stage first. A `repair_failed_tests` status has a distinct meaning: a patch was proposed, applied, and did not pass verification. Never convert all errors into patch failures.

The empirical unit for a task-general conclusion is the distinct task. The pilot is instrumentation evidence, not a statistically powered result.
