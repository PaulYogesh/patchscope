# PatchScope v0.2-alpha — Applying this build

This source package was generated from the user's original v0.1 archive (commit `9b95076b8989ff372100354d98376cf2502017c1`). Existing retrieval, repair, and v0.1 scripts were **not replaced**; the primary new code is additive.

## 1. Prepare a local development branch

```bash
cd ~/patchscope
git status --short
# If you have important uncommitted changes, commit or back them up first.
git switch -c feature/v0.2-context-interventions
```

## 2. Merge the supplied overlay into your repository

Download `PatchScope_v0.2-alpha_OVERLAY.zip`, then:

```bash
cd ~/patchscope
unzip -o ~/Downloads/PatchScope_v0.2-alpha_OVERLAY.zip -d .
git status --short
```

If the ZIP downloaded somewhere else, substitute its real location. The overlay includes README and new modules, experiments, fixtures, and tests. **It does not alter your original v0.1 model scripts** or overwrite v0.1 reports.

Alternatively, the FULL archive is a complete stand-alone source snapshot; unzip it into a **separate directory** for review rather than over the existing repo.

## 3. Run CPU checks before any model inference

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m compileall -q patchscope scripts
python -m pytest -q tests/
python -m scripts.run_experiment --manifest experiments/smoke_v02.json --dry-run
python -m scripts.run_experiment --manifest experiments/pilot_v02.json --dry-run
```

Expected dry-run counts: smoke **8**; engineering pilot **48**.

## 4. Check Qwen3.5 native structured tool calls

```bash
ollama list
PATCHSCOPE_MODEL=qwen3.5:9b python -m scripts.smoke_protocols --expect native
```

Only proceed when the smoke reports a native tool call and returns usage metadata. If your local Ollama model is tagged differently, use that exact name.

## 5. Run *one* controlled episode first

**Important:** pytest executes the model's generated patch. Temporary directories are NOT sandboxes. Inspect these small fixtures and use a machine you control. Pass the opt-in only for your known toy fixtures.

```bash
python -m scripts.run_experiment \
    --manifest experiments/smoke_v02.json \
    --model qwen3.5:9b \
    --task mini-average-001 --condition native --repetition 0 \
    --allow-trusted-execution
```

Inspect `runs/smoke-v02/mini-average-001__native__r00.json` for the complete model transcript, trajectory, token costs, patch, baseline and patched verification.

Then run remaining seven episodes:

```bash
python -m scripts.run_experiment \
    --manifest experiments/smoke_v02.json \
    --model qwen3.5:9b \
    --allow-trusted-execution --resume
python -m scripts.report_experiment --experiment smoke-v02
```

Review `reports/smoke-v02.md` before attempting the 48-run pilot. `--resume` skips any run whose JSON already exists, including failed runs; use `--force` only to deliberately rerun a complete selection.

## Tested here

- Python bytecode compilation: passed.
- **62 CPU tests**: passed in the ChatGPT sandbox, using an *external test-only BM25 substitute* because this environment could not download the pinned `rank-bm25` package.
- Deterministic 8- and 48-run schedule generation: passed.
- Four bug fixtures: each failed at baseline, passed with a fixed reference edit, and preserved the original repository.
- Scripted/fake-model native tool, proposal and patch verification tests: passed.

**Not tested here:** Actual Ollama/Qwen model calls; the pinned real `rank-bm25` installation; your GPU's inference timing; real 8- or 48-run outcomes. Please run those checks on your machine.

## Next release gate

Do not run the full 144-episode research pilot until 12 distinct, independently validated tasks are curated and the real local-model 8-/48-run smoke logs pass manual inspection. Four tiny synthetic tasks validate *engineering*, not publishable scientific results.
