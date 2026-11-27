# PatchScope — SWE-bench Lite development pilot (additive v0.7 step)

This overlay adds `patchscope/swebench_dev.py`, `scripts/run_swebench_dev.py`, and offline tests. It does **not** change the original `agent.py`, experimental manifests, old results, or Review Studio.

## Scope

- Uses the **23 SWE-bench Lite development issues** only. Does not tune on the test split.
- Clones the historical repo commit for a selected issue, then writes an **allowlisted** `public_task.json` and `issue.md` outside the checkout. Gold patches, `test_patch`, hidden evaluator labels and hindsight hints are *never serialized* into the agent's workspace.
- Calls the **existing PatchScope `run_episode` Qwen agent**, under `native` condition, with zero oracle files or preseeded context and **host-side test execution disabled**.
- If the agent proposes a one-string replacement, checks that its unified patch applies cleanly with `git apply --check`, without modifying the checked-out base state. Exports `prediction.jsonl` for the official SWE-bench Docker evaluator.
- Saves an `episode.json` with tool calls, observed source, token usage and proposal. `outcome.status` from Core may say `proposal_requires_explicit_verification_opt_in`; that is expected and **does not mean an official benchmark pass/fail**.

## Apply (Ubuntu)

Place the downloaded overlay ZIP in `$HOME` and run:

```bash
cd ~/patchscope
unzip -o ~/PatchScope_SWEbench_Dev_Pilot_Overlay.zip -d .
source .venv/bin/activate
python -m pip install datasets  # install in the CORE venv once; HF cache can be shared
python -m unittest discover -s tests -p 'test_swebench_dev.py' -v
```

**Do not** unzip this overlay into `~/PatchScope_Learning`. It extends the original research harness at `~/patchscope`, not the deterministic Studio.

## Commands

```bash
cd ~/patchscope
source .venv/bin/activate

# List the 23 public dev issue IDs; no model calls
python -m scripts.run_swebench_dev list

# Pick one EXACT instance_id from that list
python -m scripts.run_swebench_dev prepare --instance 'PASTE_DEV_INSTANCE_ID'

# Check checkout SHA and agent data boundary before inference
python -m scripts.run_swebench_dev inspect --instance 'PASTE_DEV_INSTANCE_ID'

# Run Qwen3.5:9b, using the SAME core run_episode function as before
# This does not run pytest or other repository code on the host
python -m scripts.run_swebench_dev predict --instance 'PASTE_DEV_INSTANCE_ID' --model qwen3.5:9b
```

Results live in:

```
~/patchscope_swebench_dev/<instance_id>/
  public_task.json    # allowlisted issue / repo / base_commit
  issue.md            # original public issue
  repo/               # pinned checkout; must remain unmodified
  episode.json        # complete Qwen trajectory; no hidden tests
  prediction.jsonl    # only if git apply --check passed
```

## Official independent grading (separate environment)

Install SWE-bench in its own compatible environment and Docker. Refer to its **current official CLI** for the exact harness version. For example, for one development task, its documented Python entry point is:

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --split dev \
  --predictions_path "$HOME/patchscope_swebench_dev/PASTE_DEV_INSTANCE_ID/prediction.jsonl" \
  --instance_ids PASTE_DEV_INSTANCE_ID \
  --max_workers 1 \
  --run_id patchscope-dev-first-run
```

**Never execute the benchmark repository's arbitrary pytest or setup scripts directly on the Ubuntu host.** Build and tests must run inside the official isolated evaluator. Docker availability, required dependencies, and the official evaluator are not installed or validated by this overlay.

## Known limitations

1. The current Core agent has only two read-only file tools and one strict `path/old/new` proposal. Many real GitHub issues cannot be solved with that contract; failure or no proposal is expected.
2. It lists implementation `.py` files, excluding `test_*.py`. Large repositories can generate oversized file lists and exhausted model context.
3. A `git apply --check` success proves patch applicability, not correctness.
4. Clone size may be significant; only prepare one instance initially. GitHub access and a compatible Git installation are required.
5. Importantly, this is a **dev pilot**, not a scored benchmark. Do not report a SWE-bench resolved rate until the official Docker grader runs.
6. Never report v0.6 synthetic token or performance numbers as directly comparable to this new pilot; budgets and task difficulty differ.
7. Public benchmark issue text can include adversarial or stale instructions; the present agent may follow them. The read-only tools and blocked host test execution limit the blast radius, but don't imply a complete adversarial security sandbox.

## Why this is not a LangGraph migration

Keeping the existing agent loop intact preserves its tool validation, provenance, budgets and trajectory format, while isolating the benchmark adapter. The long-term architecture can gain a `ModelBackend` interface and an optional MCP tool endpoint without invalidating the original research harness.
