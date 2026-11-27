# Apply PatchScope v0.2.4 on Ubuntu

The overlay is based on `PatchScope_v0.2.3_FULL.zip` and is intended for your
existing `~/patchscope` working tree. It does **not** include or overwrite
`runs/` or generated `reports/`. Your original 48 pilot runs are unchanged.

## Install and validate

```bash
cd ~/patchscope
unzip -o ~/PatchScope_v0.2.4_STAGE_BUDGET_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
```

## Audit the two existing v0.2.3 diagnostic runs, no new model calls

```bash
python -m scripts.audit_proposals \
  --manifest experiments/repair_diagnostic_v023.json
cat reports/repair-diagnostic-v023.proposals.md
```

## Check the new independent experiment schedule

```bash
python -m scripts.run_experiment \
  --manifest experiments/proposal_cap_v024.json --dry-run
```

## Run only two focused model experiments first

```bash
python -m scripts.run_experiment \
  --manifest experiments/proposal_cap_v024.json \
  --task mini-clamp-002 --condition oracle --repetition 0 \
  --model qwen3.5:9b --allow-trusted-execution

python -m scripts.run_experiment \
  --manifest experiments/proposal_cap_v024.json \
  --task mini-slug-003 --condition native --repetition 0 \
  --model qwen3.5:9b --allow-trusted-execution
```

## Inspect the outcome without rerunning the model

```bash
python -m scripts.audit_proposals \
  --manifest experiments/proposal_cap_v024.json
cat reports/proposal-cap-v024.proposals.md
```

These reports suppress raw source/transcript content. Share these concise
reports and the two terminal outcome lines for interpretation. Do not use
`--force` on any earlier experiment. This local code-execution workflow
is **not** sandboxed; only execute personally inspected small fixtures.

## Protocol comparison

In v0.2.3 and v0.2.4 the same task/condition/repetition has the same scheduled
model/block seed, initial prompt, evidence, temperature, and retry policy.
Only the patch-proposal completion ceiling differs. Outputs can still be
stochastic and the changed cap is a treatment, not a controlled observed-token
matching scheme. v0.2.4 has a new experiment ID to prevent mixing outcomes.
