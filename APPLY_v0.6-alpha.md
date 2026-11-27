# Apply v0.6-alpha

Apply on top of **v0.5.1**. The overlay does not replace any old fixtures or experiment results.

```bash
cd ~/patchscope
unzip -o ~/PatchScope_v0.6-alpha_PUBLIC_TRACE_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
python -m scripts.run_experiment --manifest experiments/operative-off-v060.json --condition native --dry-run
python -m scripts.run_experiment --manifest experiments/operative-trace-v060.json --condition native --dry-run
```

Run only the two fresh, trusted toy defects under each arm:

```bash
for policy in off trace; do
  python -m scripts.run_experiment \
    --manifest "experiments/operative-${policy}-v060.json" \
    --condition native --model qwen3.5:9b \
    --allow-trusted-execution --resume
done
python -m scripts.compare_operative_v060
cat reports/operative-evidence-v060.md
```

A public reproducer is run **only in the trace arm, before exploration**. This changes the exploration input, enabling the agent to inspect modules it might otherwise miss. Both arms run the same independently stored pytest verifier. Neither arm receives oracle-labeled paths. This comparison is an instrumentation test, not an estimate of causal effect generality.

CAUTION: `--allow-trusted-execution` executes Python from the repository in a process on your host. The temporary copy is not a security sandbox. Run only inspected, trusted toy fixtures. Preserve all old run directories.
