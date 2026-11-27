"""Audit recorded tool trajectories, oracle exposure, and repeated decisions.

No model is invoked and no fixture code is executed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchscope.experiment import PROJECT_ROOT, load_manifest
from patchscope.trajectory_audit import audit_experiment


def render_markdown(summary: dict) -> str:
    lines = [f"# PatchScope trajectory audit — {summary['experiment_id']}", "",
             f"Audited {summary['total_runs']} runs. Oracle localization is used for **post-hoc analysis only**; "
             "the oracle paths must not be provided to the model in native/BM25/placebo/misleading conditions.", "",
             "## Evidence and exploration", "",
             "| Condition | Runs | Oracle seeded | Wrong-locus seeded | Oracle observed | Wrong-locus patches | Off-target reads | Repeat reads | Expanded seeded reads | Verified |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for condition, row in summary["conditions"].items():
        lines.append(f"| {condition} | {row['runs']} | {row['seeded_oracle']} | "
                     f"{row['seeded_misleading']} | {row['oracle_observed']} | "
                     f"{row['wrong_locus_patches']} | {row['off_target_reads']} | "
                     f"{row['repeated_reads']} | {row['read_expansions']} | "
                     f"{row['verified_repairs']} |")
    identical = summary["identical_repeat_groups"]
    lines.extend(["", "## Repeat-trajectory diagnostics", "",
                  f"{len(identical)} task–condition groups had identical recorded decisions across all available repetitions.", ""])
    if identical:
        for group in identical:
            lines.append(f"- `{group['task_id']}` / `{group['condition']}`: "
                         f"{group['repetitions']} identical action-and-patch sequences")
    else:
        lines.append("No repeated group was perfectly identical across all recorded repetitions (or no group had multiple runs).")
    lines.extend(["", "**Interpretation:** identical decisions need not imply identical hidden reasoning. "
                  "Equal outcomes or token totals alone do not establish identical actions. "
                  "Off-target file reads are a proxy based on curated oracle labels, "
                  "not proof that an action was unnecessary. These are diagnostic metrics, "
                  "not claims of causal mediation.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    run_dir = PROJECT_ROOT / "runs" / manifest["experiment_id"]
    paths = sorted(run_dir.glob("*.json"))
    if not paths:
        parser.error(f"No runs found in {run_dir}")
    records = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    summary = audit_experiment(records, manifest)
    base = PROJECT_ROOT / "reports" / manifest["experiment_id"]
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    base.with_suffix(".audit.md").write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote {base.with_suffix('.audit.md')} and {base.with_suffix('.audit.json')} ({len(paths)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
