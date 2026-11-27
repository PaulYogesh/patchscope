# Apply PatchScope v0.2.3 on Ubuntu

Run inside your existing `~/patchscope` checkout on the
`feature/v0.2-context-interventions` branch. The ZIP does **not** touch the
existing `runs/pilot-v02` JSON files.

```bash
cd ~/patchscope
unzip -o ~/PatchScope_v0.2.3_PROPOSAL_DIAGNOSTICS_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
```

**Step 1: diagnose your old, already-recorded 48 runs without Ollama:**

```bash
python -m scripts.audit_proposals --manifest experiments/pilot_v02.json
cat reports/pilot-v02.proposals.md
```

If responses used exactly the 450-token completion ceiling, they may have been
truncated; this is a reason to inspect the evidence, not proof of truncation.
Send this compact report back before making conclusions.

**Step 2: confirm the new experiment has a separate ID and its own 16-run schedule:**

```bash
python -m scripts.run_experiment \
  --manifest experiments/repair_diagnostic_v023.json --dry-run
```

**Step 3: test two diagnostic episodes only (requires local Ollama):**

```bash
python -m scripts.run_experiment \
  --manifest experiments/repair_diagnostic_v023.json \
  --task mini-clamp-002 --condition oracle --repetition 0 \
  --model qwen3.5:9b --allow-trusted-execution

python -m scripts.run_experiment \
  --manifest experiments/repair_diagnostic_v023.json \
  --task mini-slug-003 --condition native --repetition 0 \
  --model qwen3.5:9b --allow-trusted-execution
```

Review each new run's `proposal_attempts` and `usage.usage_events`, especially
`finish_reason`, before running more episodes. Both commands execute
model-modified Python via pytest. Use only trusted synthetic fixtures.

Never use `--force` against the old pilot. Do not treat a successful proposal
correction as a verified repair unless patched tests passed after a failing
baseline. Do not compare aggregate repair rates between `pilot-v02` and
`repair-diagnostic-v023` as a causal estimate.
