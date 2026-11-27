"""Local archived-repair diagnostic. No model calls."""
import argparse
import difflib
import json
from pathlib import Path

from patchscope.repair import (
    temporary_repo,
    apply_exact_edit,
    run_pytest,
)

parser = argparse.ArgumentParser()
parser.add_argument("--allow-trusted-execution", action="store_true")
args = parser.parse_args()

tasks = [
    "retry-dynamic-dispatch-014",
    "tax-dynamic-dispatch-013",
]
arms = {
    "off": "operative-off-v060",
    "trace": "operative-trace-v060",
}

lines = [
    "# PatchScope v0.6 — repair divergence",
    "",
    "Post-hoc analysis of saved proposals. No model calls.",
    "",
]

for task_id in tasks:
    lines += [f"## {task_id}", ""]
    edits = {}

    for arm, experiment in arms.items():
        manifest = json.loads(
            Path(f"experiments/{experiment}.json").read_text()
        )
        task = next(
            t for t in manifest["tasks"]
            if t["task_id"] == task_id
        )
        repo = Path(task["repo_path"])

        record_path = (
            Path("runs") / experiment /
            f"{task_id}__native__r00.json"
        )
        record = json.loads(record_path.read_text())

        outcome = record["outcome"]
        proposal = record.get("proposal")

        lines += [
            f"### {arm}",
            f"Status: `{outcome['status']}`",
            f"Verified: `{outcome['repair_verified']}`",
            "",
        ]

        if not proposal:
            lines += ["No validated proposal.", ""]
            continue

        path = proposal["path"]
        old = proposal["old"]
        new = proposal["new"]

        source = (repo / path).read_text()

        if not old or source.count(old) != 1:
            raise RuntimeError(
                f"Patch preimage mismatch: {task_id}/{arm}"
            )

        patched = source.replace(old, new, 1)

        diff = "".join(difflib.unified_diff(
            source.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        ))

        if (record.get("proposal_diff") is not None
                and record["proposal_diff"] != diff):
            raise RuntimeError(
                f"Archived diff mismatch: {task_id}/{arm}"
            )

        edits[arm] = (path, old, new)

        lines += [
            f"Patch file: `{path}`",
            "",
            "```diff",
            diff.rstrip(),
            "```",
            "",
        ]

        if args.allow_trusted_execution:
            with temporary_repo(repo) as work:
                baseline = run_pytest(
                    work,
                    timeout=task["verification"]["timeout_seconds"],
                )
                if baseline["passed"]:
                    raise RuntimeError(
                        f"Baseline unexpectedly passed: {task_id}"
                    )

                apply_exact_edit(work, path, old, new)

                result = run_pytest(
                    work,
                    timeout=task["verification"]["timeout_seconds"],
                )

            lines += [
                "Reverified: " + (
                    "PASS" if result["passed"] else "FAIL"
                ),
                "",
            ]

            if result["passed"] != bool(
                outcome["repair_verified"]
            ):
                raise RuntimeError(
                    f"Archived result mismatch: {task_id}/{arm}"
                )

            if not result["passed"]:
                lines += [
                    "```text",
                    result["output"].replace("```", "` ` `"),
                    "```",
                    "",
                ]

    if len(edits) == 2:
        lines += [
            f"Same exact edit: `{edits['off'] == edits['trace']}`",
            "",
        ]

output = Path("reports/operative-repair-divergence-v061.md")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(lines), encoding="utf-8")

print(f"Report written: {output}")
