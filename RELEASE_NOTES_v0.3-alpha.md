# PatchScope v0.3-alpha — Genuine wrong-locus evidence

## Engineering change

Introduces an optional fifth condition, `misleading`, alongside the four v0.2
conditions. It injects **real code from a curated, task-relevant but wrong-locus
file**. The decoy code is not fabricated to the model. The same decoy file is
present in the repository for **all five conditions**, so the difference is
*initial exposure* to it, not repository contents. The file names and all code
remain retrievable using ordinary read tools in every arm.

Historical fixtures and manifests are unchanged. The new `interference_*`
fixture directories are copies with one additional wrong-locus implementation.
For each task a controlled test confirms that repairing the decoy alone does
not fix the failing tests. These are deliberately synthetic stress tests, not
evidence of a real-world performance effect.

## What to measure

- First file read and later off-target reads
- True oracle-file exposure vs wrong-locus seed exposure
- Patch targeting true or wrong-locus file (if a proposal was produced)
- Independently verified repairs, protocol failures, and token cost
- Matched task-level comparisons; avoid claiming population effects from four tasks

## Budget calibration

The v0.2.4 result showed a 450-token proposal limit truncated a slug repair;
1,400 completion tokens yielded a verified repair. v0.3 uses a 1,400-token
proposal ceiling and one contract retry, while retaining 450 for exploration.
This is a **new experimental protocol**, not an extension of the original v0.2
repair-rate dataset. Keep run records separate.

## Limitations

Curated duplicated functions make the misleading arm somewhat artificial.
Length/format matching remains approximate, and adding a decoy alters BM25's
retrieval corpus. This is intentional inside the v0.3 experiment; do not
compare it directly to the historical four-fixture pilot. BM25 and oracle may
still overlap for some tasks. Do not regard 20 engineering episodes as 20
independent tasks. Run only trusted local fixtures; tempfile is not a security
sandbox. Real Qwen model calls must be validated on the Ubuntu workstation.
