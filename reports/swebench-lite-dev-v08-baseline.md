# SWE-bench Lite development baseline

The frozen v0.8 batch recorded 23 episodes and exported 8 predictions
(34.8% of the assigned issues). The exported diffs passed the preflight
applicability check. This table records generation outcomes from the batch
transcript. A paired benchmark result requires the v0.9 episodes and the
official grader outputs for both arms.

| Terminal generation outcome | Issues |
|---|---:|
| Prediction exported | 8 |
| Original fragment was repeated in observed source | 7 |
| Soft token budget exhausted | 5 |
| Proposal JSON invalid or missing | 2 |
| Tool protocol error | 1 |

The 23 issues informed development. They can identify where the pipeline
loses proposals and support a paired development comparison.

| Issue | v0.8 generation |
|---|---|
| `sqlfluff__sqlfluff-1625` | Exported |
| `sqlfluff__sqlfluff-2419` | patch_json_invalid_or_missing |
| `sqlfluff__sqlfluff-1733` | patch_old_not_unique_in_observed |
| `sqlfluff__sqlfluff-1517` | soft_token_budget_exhausted |
| `sqlfluff__sqlfluff-1763` | soft_token_budget_exhausted |
| `marshmallow-code__marshmallow-1359` | patch_old_not_unique_in_observed |
| `marshmallow-code__marshmallow-1343` | Exported |
| `pvlib__pvlib-python-1707` | protocol_error |
| `pvlib__pvlib-python-1072` | patch_json_invalid_or_missing |
| `pvlib__pvlib-python-1606` | patch_old_not_unique_in_observed |
| `pvlib__pvlib-python-1854` | soft_token_budget_exhausted |
| `pvlib__pvlib-python-1154` | patch_old_not_unique_in_observed |
| `pylint-dev__astroid-1978` | Exported |
| `pylint-dev__astroid-1333` | Exported |
| `pylint-dev__astroid-1196` | patch_old_not_unique_in_observed |
| `pylint-dev__astroid-1866` | patch_old_not_unique_in_observed |
| `pylint-dev__astroid-1268` | Exported |
| `pyvista__pyvista-4315` | soft_token_budget_exhausted |
| `pydicom__pydicom-1694` | soft_token_budget_exhausted |
| `pydicom__pydicom-1413` | Exported |
| `pydicom__pydicom-901` | Exported |
| `pydicom__pydicom-1139` | patch_old_not_unique_in_observed |
| `pydicom__pydicom-1256` | Exported |

For the paired report command and the editor comparison design, see
[the development protocol](../SWE_BENCH_DEV_PAIRED_REPORT.md).
