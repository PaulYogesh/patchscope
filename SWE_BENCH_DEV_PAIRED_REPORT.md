# PatchScope development comparison

The [historical baseline](reports/swebench-lite-dev-v08-baseline.md) records
the v0.8 export outcomes for 23 SWE-bench Lite development issues. The report
command joins saved episodes, exported predictions and official grader
outputs by issue ID. Each independently graded arm uses a separate run ID.

## Generate the v0.9 comparison arm

On the machine with the existing PatchScope and benchmark environments, use
the same Qwen model build and settings as the frozen v0.8 run. Check the
local model digest if you recorded it. The model name alone cannot establish
that its weights are identical. The batch below resumes completed episodes
and lets you smoke-test the first issue by setting `PATCHSCOPE_MAX_ISSUES=1`.

```bash
cd ~/patchscope
set -o pipefail
instances=reports/swebench-lite-dev-23.txt
v09_root="$HOME/patchscope_swebench_dev_v09"
v09_logs="$HOME/patchscope_swebench_eval/batch_v09/logs"
mkdir -p "$v09_root" "$v09_logs"
processed=0
while IFS= read -r instance; do
  if [ -f "$v09_root/$instance/episode.json" ]; then
    printf 'Existing episode for %s\n' "$instance"
  else
    if [ ! -e "$v09_root/$instance" ]; then
      ./.venv/bin/python -m scripts.run_swebench_dev prepare \
        --instance "$instance" --workspace-root "$v09_root" || break
    fi
    ./.venv/bin/python -m scripts.run_swebench_dev predict \
      --instance "$instance" --workspace-root "$v09_root" \
      --model qwen3.5:9b --max-steps 10 \
      2>&1 | tee "$v09_logs/$instance.predict.log" || break
  fi
  processed=$((processed + 1))
  if [ "$processed" -ge "${PATCHSCOPE_MAX_ISSUES:-23}" ]; then
    break
  fi
done < "$instances"
printf 'Episodes present for %s assigned issues in this pass\n' "$processed"
```

In the existing SWE-bench grader environment, collect just the v0.9 exports
and grade them using the same evaluator version, dataset split and
configuration as v0.8. The baseline uses the original v0.8 exports. For
example, from the evaluation directory with the grader environment active:

```bash
cd ~/patchscope_swebench_eval
instances="$HOME/patchscope/reports/swebench-lite-dev-23.txt"
v09_root="$HOME/patchscope_swebench_dev_v09"
while IFS= read -r instance; do
  if [ -f "$v09_root/$instance/prediction.jsonl" ]; then
    cat "$v09_root/$instance/prediction.jsonl"
  fi
done < "$instances" > patchscope-v09-dev-predictions.jsonl

if [ -s patchscope-v09-dev-predictions.jsonl ]; then
  python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite --split dev \
    --predictions_path "$PWD/patchscope-v09-dev-predictions.jsonl" \
    --max_workers 1 --run_id patchscope-v09-dev-paired
fi
```

## Generate the reviewable result

Substitute the two actual aggregate grader JSON paths and, if available, the
parents of the per-issue grader directories for the same runs.

```bash
cd ~/patchscope
./.venv/bin/python -m scripts.report_swebench_dev_pair \
  --instances reports/swebench-lite-dev-23.txt \
  --baseline "$HOME/patchscope_swebench_dev_v08" \
  --candidate "$HOME/patchscope_swebench_dev_v09" \
  --baseline-grader /path/to/old-run.json \
  --candidate-grader /path/to/new-run.json \
  --baseline-grader-root /path/to/old-run-model-dir \
  --candidate-grader-root /path/to/new-run-model-dir \
  > reports/swebench-lite-dev-paired.md
```

Omit either grader flag when its outputs are unavailable. Use `--format json`
for the per-issue settings checks and usage coverage. The paired counts use
matching recorded benchmark, issue, model generation settings, budgets and
condition. The report exposes missing, ungraded and ambiguous cases. A
completed run with no prediction contributes a non-resolution. An exported
prediction without a clear grader outcome keeps its resolution unknown.
Review the changed cases for semantic correctness using independent
verification. The 23 development issues provide an engineering screen.
Use untouched issues for a generalization claim.

## Compare with an established editor

Use the v0.9 setup as the baseline and a pinned oh-my-pi editor as a new
arm. Verify its native prompt and edit format before using the same
starting commits, model build, initial code access, budgets and grader.
Preserve the adapter revision and record adapter effort. Keep any shared
static review policy fixed if the objective is to isolate the editor
format. If native validation differs, describe the comparison as an
editor-and-validation comparison. Compare output applicability and
independently graded resolutions first, then total tokens and elapsed
time. Record protocol changes and any differences in the grading
environment alongside the result.

The paired reporting command accepts the two saved arms once the external
editor has a compatible adapter. The editor integration and its measured
results are follow-up work.

## Diagnose empty proposals at the completion limit

The v0.9 development run on `sqlfluff__sqlfluff-1733` returned zero visible
characters on both proposal attempts. Both stopped at the 1,600-token
completion limit. No proposal reached static review. Test whether a
compatible Ollama backend produces visible output with thinking disabled
for proposal calls. Use a separate workspace to preserve the control.

```bash
issue=sqlfluff__sqlfluff-1733
workspace="$HOME/patchscope_swebench_dev_v09_no_proposal_thinking"
if [ ! -d "$workspace/$issue" ]; then
  python -m scripts.run_swebench_dev prepare --instance "$issue" --workspace-root "$workspace"
fi
python -m scripts.run_swebench_dev predict --instance "$issue" --workspace-root "$workspace" \
  --model qwen3.5:9b --max-steps 10 --proposal-reasoning-effort none
```

The request uses Ollama's OpenAI-compatible `reasoning_effort` option.
Check the installed server and model support before interpreting the result.
The episode records the requested policy, visible response length and whether
the server exposed reasoning output. Missing reasoning output alone cannot
confirm that the backend applied the option. The paired report marks the
generation settings as different. Treat this as a separate intervention
and check export and official resolution independently.

[Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)

The opt-in run on this issue produced 329 visible characters and stopped
normally after 105 completion tokens. It exported on the first attempt.
Inspection found a duplicate decorator and a merged comment. The model
selected fully observed lines 68–71, but copied a partial comment from
line 72 into a replacement without a final newline. The resulting join
passed static review and Git preflight.

The line-range contract now rejects a nonempty replacement that would join
to a following original line. The agent can retry this rejection within the
existing budget. Preserve the earlier export for grading as submitted. Use
a fresh workspace when measuring the updated contract and record its code
revision.

On the development case, the original export and the boundary-checked retry
both graded unresolved. The new validator rejected the missing final newline
on attempt 1. The grader applied attempt 2. The target test still failed and
the three recorded regression tests passed. The new diff preserved the
following comment line and still duplicated a decorator. It added a partial
comment without changing the indentation calculation.

## Test a smaller file inventory

The earlier episode returned 219 paths in an 8,163-character inventory and
carried that response into the remaining exploration requests. The exploration
reserve stopped that run after a truncated read. The opt-in file inventory
limit previews a fixed number of sorted paths and reports when more exist.
Search and file reads retain their existing scope. Keep the model, reasoning
setting, line-boundary check and token budgets fixed. In a fresh workspace,
add `--file-inventory-limit 40` to the prediction command above. Compare
exploration prompt tokens, source reads, patch contents and official grade
with the boundary-checked run. Treat this as a separate development variant
and use the original evaluator configuration.

The four-issue inventory pilot exported zero patches with the full inventory
and one unresolved patch with the preview. Neither setting resolved an issue.
Total tokens were 53,646 and 55,981 respectively. Keep the preview opt-in.

### Astroid retry-budget experiment

The full-inventory Astroid run never saw line 470 and proposed deleting it
twice. The preview read lines 460–500 and 430–480, covering line 474. Its
first proposal was rejected for a missing final newline. The retry was
requested at 16,613 tokens and blocked by the 16,000-token soft total budget.
In the recorded preview, the second range read came at 10,362 tokens. One
further exploration request raised usage to 13,814 tokens.

On a fresh workspace, keep the 40-path preview and proposal thinking off.
Try `--proposal-reserve-tokens 6000` to move the handoff threshold from
11,500 to 10,000 tokens. On the recorded path this would stop after the
second range read and before the extra search. The total ceiling remains
16,000. The reserve is checked after exploration responses, so it cannot
guarantee headroom or identical model behavior on a rerun. Check whether a
retry completes and send any exported patch to the official evaluator.

## Investigating an unresolved prediction

Add `--diagnose-unresolved` to the paired report command and supply the per-arm grader roots and official aggregate reports. Markdown and JSON then include test-group outcomes for each officially unresolved prediction. Missing test evidence stays unknown. The official resolution counts still come from the grader.

With an existing, independently graded reference, add `--reference-control BASE REFERENCE_JSONL REFERENCE_REPORT`. BASE is the 40-character base commit for that reference. The JSONL is a single evaluator-supplied reference prediction for the issue. REFERENCE_REPORT points to its separate official per-issue report under the run/model/issue directory. Repeat the option for additional issues. Keep references outside the agent workspace. The report compares the applied Git trees, lists the reference outcomes, and checks grader patch.diff files against the submitted artifacts when available. The caller supplies the provenance of the reference prediction and selects matching benchmark and grader environments.

The [pydicom #811 case](docs/cases/pydicom-811.md) shows an exact tree match and an existing filename test that failed for both model and reference. The original development trial retains its unresolved grade.
