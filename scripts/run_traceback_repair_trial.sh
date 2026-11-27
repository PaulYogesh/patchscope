#!/usr/bin/env bash
# Optional argument resumes the printed pilot directory after interruption.
set -euo pipefail
cd "$(dirname "$0")/.."
repo="$PWD"
pilot="${1:-$(mktemp -d "$HOME/patchscope_traceback_trial.XXXXXX")}"
pilot="$(realpath "$pilot")"
eval_dir="$HOME/patchscope_swebench_eval"
grader="$HOME/patchscope_swebench_grader_venv/bin/python"
python="$repo/.venv/bin/python"
model="qwen3.5:9b"
test -x "$grader"
test -d "$eval_dir"
printf 'Pilot directory: %s\n' "$pilot"
exec 9>"$pilot/run.lock"
flock -n 9 || { echo "Trial is already running"; exit 1; }
"$python" -m scripts.trial_traceback_repair "$pilot"
mapfile -t issues < "$pilot/instances.txt"
args=(--instances "$pilot/instances.txt")
for arm in baseline candidate; do
  args+=("--$arm" "$pilot/$arm")
  exports=()
  preds="$pilot/$arm-exports.jsonl"
  : > "$preds"
  for issue in "${issues[@]}"; do
    file="$pilot/$arm/$issue/prediction.jsonl"
    if [[ -s "$file" ]]; then
      cat "$file" >> "$preds"
      exports+=("$issue")
    fi
  done
  if (( ${#exports[@]} )); then
    run="ps_trace_trial_${pilot##*.}_$arm"
    (cd "$eval_dir" && "$grader" -m swebench.harness.run_evaluation \
       --dataset_name SWE-bench/SWE-bench --split dev --instance_ids "${exports[@]}" \
       --predictions_path "$preds" --max_workers 1 --run_id "$run")
    args+=("--$arm-grader" "$eval_dir/$model.$run.json"
           "--$arm-grader-root" "$eval_dir/logs/run_evaluation/$run/$model")
  fi
done
"$python" -m scripts.report_swebench_dev_pair "${args[@]}" > "$pilot/grades.md"
cat "$pilot/localization.md" "$pilot/grades.md" > "$pilot/paired-report.md"
cat "$pilot/grades.md"
printf 'Report: %s/paired-report.md\n' "$pilot"
