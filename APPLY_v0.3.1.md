# PatchScope v0.3.1 — Decoy-presence counterfactual

This update is **additive** over v0.3-alpha. It does not change the agent, its prompts, its retrieval algorithm, its budgets, or the original 20-run results.

## Why

In the five-condition engineering smoke, both `native` and `misleading` made wrong-locus edits on three out of four tasks. That means **the presence of tempting decoy source files** may matter even without explicit injected evidence. Comparing `misleading` with `native` in the same decoy-containing repo cannot identify the contribution of *decoy existence*.

v0.3.1 evaluates the **repository-composition counterfactual**: native exploration on an otherwise byte-identical fixture **with** versus **without** a single curated decoy file.

## Apply

From `~/patchscope` (v0.3-alpha already installed):

```bash
unzip -o ~/PatchScope_v0.3.1_DECOY_CONTROL_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
```

## Validate schedule: no model calls

```bash
python -m scripts.run_experiment \
  --manifest experiments/decoy_free_native_v031.json \
  --condition native --dry-run
```

This should show exactly **four native runs**, one per task. The seeds must match `native` runs already present in `interference-smoke-v030`.

## Execute ONLY four new runs

```bash
python -m scripts.run_experiment \
  --manifest experiments/decoy_free_native_v031.json \
  --condition native \
  --model qwen3.5:9b \
  --allow-trusted-execution \
  --resume
```

**Safety:** this runs model-edited Python test code on your workstation. Temporary copies are not isolation sandboxes. Only use the bundled inspected toy fixtures.

## Compare against EXISTING v0.3 native records without rerunning them

```bash
python -m scripts.compare_decoy_presence
cat reports/decoy-presence-v031.md
```

The comparison checks:
- Every source, test, and issue file shared between the two variants has identical bytes.
- Exactly **one wrong-locus source file** exists only in the decoy-present variant.
- Task IDs, repetitions, generation seed, model digest, prompt version, tools, generation configuration, and budgets match.
- Every pair has explicit verification status.

It then reports repair flips, selected patch path, wrong-locus edits, and per-run token deltas. It refuses missing or mismatched pairs.

## Interpretation

This experiment isolates the effect of **adding a decoy file to repository inventory**, not the incremental effect of *seeding* misleading evidence. The native model can read the decoy even when it is not seeded. This is an engineering demonstration across only four synthetic tasks; avoid scientific significance claims. It is not a substitute for a curated real-task benchmark or repeated controlled experiments across a broader task population.

Do **not** edit or rerun `interference_smoke_v030.json`. Reuse its existing `runs/interference-smoke-v030/` JSON files.
