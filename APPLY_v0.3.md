# Apply PatchScope v0.3-alpha to existing v0.2.4 checkout

No GitHub push is required.

```bash
cd ~/patchscope
# Optional local checkpoint; run `git status` first if uncommitted changes matter.
# git add -A && git commit -m "Checkpoint v0.2.4 before interference pilot"

unzip -o ~/PatchScope_v0.3-alpha_INTERFERENCE_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
```

## Stage 1: verify the randomized 20-run plan (no LLM calls)

```bash
python -m scripts.run_experiment \
  --manifest experiments/interference_smoke_v030.json --dry-run
```

## Stage 2: run first matched block on the clamp defect

Run the two most informative arms first (one or both):

```bash
python -m scripts.run_experiment \
  --manifest experiments/interference_smoke_v030.json \
  --task mini-clamp-002 --condition oracle --repetition 0 \
  --model qwen3.5:9b --allow-trusted-execution

python -m scripts.run_experiment \
  --manifest experiments/interference_smoke_v030.json \
  --task mini-clamp-002 --condition misleading --repetition 0 \
  --model qwen3.5:9b --allow-trusted-execution
```

**Caution:** pytest runs model-edited trusted local code on your actual host.
A temporary copy is not an OS sandbox.

## Stage 3: complete the smoke pilot after reviewing the first two records

```bash
python -m scripts.run_experiment \
  --manifest experiments/interference_smoke_v030.json \
  --model qwen3.5:9b --allow-trusted-execution --resume

python -m scripts.report_experiment --experiment interference-smoke-v030
python -m scripts.audit_experiment \
  --manifest experiments/interference_smoke_v030.json
python -m scripts.audit_proposals \
  --manifest experiments/interference_smoke_v030.json
```

Upload these reports for joint interpretation:
`reports/interference-smoke-v030.md`,
`reports/interference-smoke-v030.audit.md`, and
`reports/interference-smoke-v030.proposals.md`.

The original v0.2 experiment records and analysis remain intact.
