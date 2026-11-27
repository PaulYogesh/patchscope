"""Generate a neutral Markdown report from recorded experimental outcomes."""
from __future__ import annotations

import argparse
import json

from patchscope.analysis import summarize
from patchscope.experiment import PROJECT_ROOT


def fmt(x, digits=3):
    return "—" if x is None else f"{x:.{digits}f}"


def build_report(records: list[dict], experiment_id: str) -> str:
    s = summarize(records)
    lines = [
        f"# PatchScope v0.2 — {experiment_id}", "",
        "## Protocol", "",
        "Recorded context conditions: " + ", ".join(sorted(s["conditions"])) + ". "
        "Interventions were assigned deterministic randomized order within "
        "(task, repetition) blocks, with matched model seeds. Misleading, when "
        "present, seeds genuine task-relevant code from a curated wrong-locus "
        "repository file, not fabricated source content.", "",
        "Only verified passing tests *after* a failing baseline count as repairs. "
        "A model patch is not a verified repair.", "",
        f"## Sample: {s['task_count']} tasks, {s['total_runs']} recorded runs", "",
        "## Outcome summary", "",
        "| Condition | Runs | Evaluated | Verified | Repair rate | Median tokens | Median tools | Repeated reads | Proposal rejects | Recovered | Protocol errors | Unverified |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, row in s["conditions"].items():
        lines.append(f"| {condition} | {row['runs']} | {row['evaluated']} | {row['verified_repairs']} | "
                     f"{fmt(row['repair_rate'])} | {fmt(row['median_tokens'], 0)} | "
                     f"{fmt(row['median_tool_calls'], 1)} | {fmt(row['median_repeated_reads'], 1)} | "
                     f"{row['proposal_rejections']} | {row['contract_recovered_runs']} | "
                     f"{row['protocol_errors']} | {row['unverified']} |")
    lines += ["", "## Paired comparisons", "",
              "| Comparison | Matched pairs | Risk difference | Task-cluster 95% CI | A-only / B-only | Exact McNemar p | Median Δ tokens |",
              "|---|---:|---:|---|---:|---:|---:|"]
    for contrast, row in s["paired_contrasts"].items():
        ci = ("—" if row["bootstrap_95_low"] is None
              else f"[{fmt(row['bootstrap_95_low'])}, {fmt(row['bootstrap_95_high'])}]")
        lines.append(f"| {contrast} | {row['matched_pairs']} | "
                     f"{fmt(row['repair_risk_difference'])} | {ci} | "
                     f"{row['a_only']} / {row['b_only']} | "
                     f"{fmt(row['exact_mcnemar_p'])} | {fmt(row['median_token_difference'], 0)} |")
    lines += [
        "", "Confidence intervals resample **tasks**, not individual repetitions. "
        "Intervals are omitted when fewer than two tasks are paired. "
        "The small pilot is for instrumentation and effect estimation, not "
        "for asserting a statistically established performance advantage. "
        "Runs with verification explicitly disabled are excluded from the "
        "repair-rate denominator and paired outcomes; model/protocol failures "
        "are counted as failures. **McNemar p-values are omitted when matched "
        "pairs include repeated observations from the same task** because those "
        "pairs are not independent. Discordance counts remain descriptive.", "",
        "## Tool and runtime behavior", "",
        "The raw JSON records contain the per-call prompt/completion usage, "
        "full visible transcript, validated tools, repeated reads, and test events.", "",
    ]
    for condition, row in s["conditions"].items():
        lines.append(f"- **{condition}:** median retrieval {fmt(row['median_retrieval_ms'])} ms; "
                     f"median wall time {fmt(row['median_wall_seconds'])} s.")
    provenance = [r.get("provenance", {}) for r in records]
    if provenance:
        p = provenance[0]
        ollama = p.get("ollama", {})
        gen = p.get("generation", {})
        lines += ["", "## Reproducibility provenance", "",
                  f"- Model: `{gen.get('model', 'unknown')}`",
                  f"- Model digest: `{ollama.get('digest', 'unknown')}`",
                  f"- Ollama: `{ollama.get('version', 'unknown')}`",
                  f"- Git commit: `{p.get('git_commit', 'unknown')}`",
                  f"- Working tree dirty: `{p.get('git_worktree_dirty', 'unknown')}`",
                  f"- Source and fixture SHA256: `{p.get('source_tree_sha256', 'unknown')}`",
                  f"- Manifest SHA256: `{p.get('manifest_sha256', 'unknown')}`",
                  f"- Prompt version: `{p.get('prompt_version', 'unknown')}`",
                  f"- Tool schema SHA256: `{p.get('tool_schema_sha256', 'unknown')}`", ""]
    lines += [
        "## Methodology", "",
        "```mermaid", "flowchart LR",
        "  A[Task and repetition] --> B[Randomized context intervention]",
        "  B --> C[Same agent and allowed read tools]",
        "  C --> D[Patch proposal]",
        "  D --> E[Disposable trusted fixture copy]",
        "  E --> F[Baseline and patched pytest]",
        "  F --> G[Structured logs and paired statistics]", "```", "",
        "## Limitations", "",
        "- Context conditions are not a substitute for a larger, curated sample of real software defects.",
        "- Oracle localization is privileged evaluator data and measures available headroom.",
        "- Curated placebo and misleading code are only approximately length matched; see per-run length-gap metadata.",
        "- Misleading decoys are deliberately synthetic wrong-locus implementations; evaluate on more natural repositories before generalizing.",
        "- A temporary copy does not sandbox test execution; execution requires explicit local opt-in.",
        "- Temperature zero and a model seed do not guarantee perfectly repeatable inference.",
        "- Missing or unverified outcomes must not be interpreted as verified repairs.", "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args(argv)
    if not args.experiment.replace("-", "").replace("_", "").isalnum():
        parser.error("Invalid experiment ID")
    run_dir = PROJECT_ROOT / "runs" / args.experiment
    paths = sorted(run_dir.glob("*.json"))
    if not paths:
        parser.error(f"No completed run records under {run_dir}")
    records = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    for r in records:
        if r.get("experiment_id") != args.experiment or r.get("schema_version") != 2:
            parser.error(f"Mismatched record: {r.get('run_id')}")
    report = build_report(records, args.experiment)
    output = PROJECT_ROOT / "reports" / (args.experiment + ".md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output} ({len(records)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
