# Apply PatchScope v0.5.1 — Frozen proposal replay

This additive update is for your existing **v0.5-alpha repository**. It does not
modify the v0.5 agent, fixtures, experiments or archived run files.

```bash
cd ~/patchscope
unzip -o ~/PatchScope_v0.5.1_FROZEN_REPLAY_OVERLAY.zip -d .
source .venv/bin/activate
python -m pytest -q tests/
```

## 1. Validate the frozen protocol without Ollama

```bash
python -m scripts.replay_frozen_v051 --dry-run
```

This requires your saved `runs/interference-smoke-v030` native records. It
checks task, original model seed, issue text and that every source excerpt
previously shown to the agent still exactly matches the repository.

## 2. Replay just one task first

```bash
python -m scripts.replay_frozen_v051 \
  --task mini-average-001 \
  --model qwen3.5:9b \
  --allow-trusted-execution \
  --resume
```

## 3. Finish remaining frozen proposals

```bash
python -m scripts.replay_frozen_v051 \
  --model qwen3.5:9b \
  --allow-trusted-execution \
  --resume

python -m scripts.compare_frozen_v051
cat reports/frozen-proposal-v051.md
```

**Safety:** `--allow-trusted-execution` opts into executing generated edits
in a temporary copy of bundled trusted fixtures. A temporary directory is
NOT a security sandbox. Never use this command on unknown repositories.

**Cost:** 4 distinct tasks × 3 policies = 12 independent *proposal-only*
episodes, normally one model call each (up to one bounded JSON retry). It
runs no exploration model calls. Each policy receives the identical source
snapshot reconstructed from a single archived v0.3 native run.

**Limitations:** This isolates final-patch prompting given frozen evidence. It
does NOT measure entire agent performance, and import maps with zero edges
cannot establish a source dependency. Different prompt lengths and Qwen's
possible nondeterminism remain. Model digests must match archived evidence.

The old v0.5 `evidence-policy-v050.md` results are retained as historical
observations, not silently replaced.
