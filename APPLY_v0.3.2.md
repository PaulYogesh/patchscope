# PatchScope v0.3.2 — same-filename neutral-content control

## Apply (over v0.3.1)

```bash
cd ~/patchscope
unzip -o ~/PatchScope_v0.3.2_CONTENT_CONTROL_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
```

## Run four new native episodes

```bash
python -m scripts.run_experiment \
  --manifest experiments/same_name_neutral_v032.json \
  --condition native --dry-run

python -m scripts.run_experiment \
  --manifest experiments/same_name_neutral_v032.json \
  --condition native --model qwen3.5:9b \
  --allow-trusted-execution --resume
```

`--allow-trusted-execution` executes model-edited source with pytest on your host.
Temporary copies are **not** security sandboxes. Only run on small, inspected,
trusted synthetic fixtures. No need to rerun the previous native episodes.

## Produce controlled three-way report

```bash
python -m scripts.compare_decoy_content
cat reports/decoy-content-v032.md
```

Comparison data are read from the three separate experiment IDs:

- `decoy-free-native-v031` — original clean repository (4 existing runs)
- `same-name-neutral-native-v032` — one added neutral module (4 new runs)
- `interference-smoke-v030` — one added task-relevant decoy module (4 existing native runs)

The tool verifies exact shared file bytes, one same-name added source file,
near-equal extra-file length, validated model and seed settings, provenance,
and successful test-verification opt-in. It rejects incomplete/mismatched runs.

Do not treat four synthetic tasks as a publishable causal estimate or infer
hidden reasoning from differing patches. The neutral↔decoy comparison fixes
filename and repository file count, but code content and possibly tokenization
differ; neither variant is equivalent to a randomized evidence-seeding contrast.

**Do not push to GitHub yet**; the next milestone is diverse naturalistic tasks
and a preregistered evaluation protocol.
