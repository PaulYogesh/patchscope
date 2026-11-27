# PatchScope — decoy presence counterfactual (native exploration)

Compared 4 matched episodes across 4 distinct tasks.
The clean fixture has exactly the same shared files and issue/test bytes as the decoy fixture, but the decoy fixture adds one curated wrong-locus source file. The model, random seed, prompt/tool protocol and budgets are checked for equality.

| Task | Clean outcome | Decoy-present outcome | Clean patch | Decoy-present patch | Wrong-locus edit | Δ tokens |
|---|---|---|---|---|---|---:|
| `mini-average-001` | resolved | repair_failed_tests | `calculator.py` | `average_utils.py` | yes | +388 |
| `mini-clamp-002` | resolved | repair_failed_tests | `limits.py` | `bounds_compat.py` | yes | +937 |
| `mini-discount-004` | resolved | resolved | `checkout.py` | `checkout.py` | no | -507 |
| `mini-slug-003` | resolved | repair_failed_tests | `text_ops.py` | `slugify.py` | yes | +534 |

## Descriptive summary

- Clean verified: **4/4**
- Decoy-present verified: **1/4**
- Lost verified repair with decoy present: **3**
- Gained verified repair with decoy present: **0**
- Wrong-locus patches with decoy present: **3**
- Identical recorded action/patch sequences: **0**
- Median decoy-minus-clean tokens: **+461.0**

## Interpretation and limitations

This is a controlled **repository-composition** comparison, not the incremental effect of injecting a misleading seed. Decoy code is absent in one environment and present, readable, and retrievable in the other. Adding a file can change file lists, BM25 scores and exploration choices. All of these are part of this treatment, not separately identified mechanisms.

The four synthetic tasks are not sufficient for a population claim. Model seeds and generator configuration are matched, but local model execution may not be perfectly deterministic. No independence or significance claim is made for within-task repetitions. Verified success requires baseline failure and patched-test success; review underlying JSON and edited diffs for individual cases.
