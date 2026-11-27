# Applying PatchScope v0.5-alpha (proposal-stage reference intervention)

This ZIP is an **overlay** for the user's verified v0.4.1 tree. It does not include prior versions and does not replace historical manifests or results. `evidence_policy` defaults to `off`, preserving old agent behavior. This intervention is a research control, not a proven mitigation.

1. From `~/patchscope` (on the existing development branch), optionally commit or back up existing changes.
2. `unzip -o ~/PatchScope_v0.5-alpha_REFERENCE_MAP_OVERLAY.zip -d .`
3. `source .venv/bin/activate && python -m pytest -q tests/`
4. Dry-run: `python -m scripts.run_experiment --manifest experiments/evidence_imports_v050.json --condition native --dry-run`
5. Only trusted bundled fixtures: run each new intervention separately:

```bash
for policy in inventory imports; do
  python -m scripts.run_experiment \
    --manifest "experiments/evidence_${policy}_v050.json" \
    --condition native --model qwen3.5:9b \
    --allow-trusted-execution --resume
done

python -m scripts.compare_evidence_v050
cat reports/evidence-policy-v050.md
```

Historical baseline `runs/interference-smoke-v030/*__native__*.json` must already exist; it is not recomputed. The comparator rejects missing, mixed-seed, mixed-model, or changed-budget records. It distinguishes matching observed exploration logs from mismatches.

## Optional regression on eight already inspected benchmark tasks

```bash
for policy in inventory imports; do
  python -m scripts.run_experiment \
    --manifest "experiments/evidence_benchmark_${policy}_v050.json" \
    --condition native --model qwen3.5:9b \
    --allow-trusted-execution --resume
done
python -m scripts.compare_evidence_v050 \
  --baseline benchmark-decoy-v040 \
  --inventory evidence-benchmark-inventory-v050 \
  --imports evidence-benchmark-imports-v050
```

This comparison overwrites only `reports/evidence-policy-v050.*`; save the earlier report first if running both groups. None of these tasks are statistically independent samples of repositories, and none is reserved as unseen evaluation data.

## Design and limitations

- Exploration prompts, native tools, task seeds, and per-call budgets are unchanged. The new note is injected **only when constructing the final patch proposal**.
- `inventory` gives source filenames and limitations without importer edges. `imports` gives the same file inventory plus a static source-import reference map. This is *not* token-length matched; interpret costs cautiously.
- Static edges come from AST parsing of allowed non-test Python files; no test execution, gold `oracle` metadata, or privileged test imports are included in the note. `from . import x` and dynamic code are not proven reachable. Absence of an edge is inconclusive and must not block edits.
- The original four tasks lack resolvable import edges. A null result there is plausible. Any positive result needs independent replication with held-out repositories and a stronger execution-path signal.
- Source-map metadata (policy, sha256, number of edges and characters) is logged. Prompt text remains in the proposal transcript for local auditing.
- `--allow-trusted-execution` executes model-generated Python on the host. Only use inspected, trusted toy fixtures; temp folders are NOT security sandboxes.
