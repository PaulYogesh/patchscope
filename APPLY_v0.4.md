# Apply PatchScope v0.4-alpha

From `~/patchscope` (the existing v0.3.2 repository):

```bash
# Optional: save your work before applying an overlay
 git status --short
 unzip -o ~/PatchScope_v0.4-alpha_BENCHMARK_OVERLAY.zip -d .
 source .venv/bin/activate
 python -m pytest -q tests/
 python -m scripts.run_experiment \
   --manifest experiments/benchmark-clean-v040.json \
   --condition native --dry-run
```

The v0.4 update introduces *new* experiment identifiers. First verify the eight
fixture contracts on your machine, then run the native arm in all three
variants. **Only execute the trusted bundled toy fixtures**, as pytest runs
agent-generated edits on the host; temporary-directory copying is not an
execution sandbox.

```bash
for variant in clean neutral decoy; do
  python -m scripts.run_experiment \
    --manifest "experiments/benchmark-${variant}-v040.json" \
    --condition native --model qwen3.5:9b \
    --allow-trusted-execution --resume
done

python -m scripts.compare_benchmark_v040
cat reports/benchmark-content-v040.md
```

If a run is skipped due to `--resume`, inspect its saved JSON and provenance
before considering the three-way comparison complete. The comparison itself
rejects missing runs and mismatched model/protocol identifiers.

**No GitHub push required** at this stage; preserve raw records and iterate.
