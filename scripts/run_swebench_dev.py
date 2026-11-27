"""External benchmark pilot: public dev issue -> pinned repo -> Qwen patch.

Preparation clones public GitHub source, but never executes it. Prediction
uses the ORIGINAL PatchScope agent without any pytest execution; grade with
the official Docker harness separately.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from patchscope.swebench_dev import (
    INSTANCE_RE, BenchmarkAdapterError, dev_rows, external_manifest, find_dev_row,
    load_prepared, prepare_dev_instance, public_task, run_local_pilot,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "prepare", "predict", "inspect"])
    parser.add_argument("--instance", help="SWE-bench Lite dev instance_id")
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "patchscope_swebench_dev")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--proposal-reasoning-effort", choices=["none"],
                        help="Request thinking off for proposals on a compatible backend")
    parser.add_argument("--file-inventory-limit", type=int,
                        help="Preview at most this many paths in list_files responses")
    parser.add_argument("--proposal-reserve-tokens", type=int,
                        help="Stop exploration earlier to leave this many tokens for proposals")
    parser.add_argument("--behavioral-proposal", action="store_true",
                        help="Ask the proposer to target a concrete change in reported behavior")
    parser.add_argument("--tool-call-recovery", action="store_true",
                        help="Allow one correction for a ranged read_file call")
    parser.add_argument("--matched-source", action="store_true",
                        help="Give the proposer the same full source files as the Aider comparison")
    args = parser.parse_args(argv)
    if args.max_steps < 1 or args.max_steps > 30:
        parser.error("--max-steps must be between 1 and 30")
    if args.command == "list":
        rows = dev_rows()
        for row in rows:
            public = public_task(row)
            print(f"{public['instance_id']:<48} {public['repo']}")
        print(f"Development instances: {len(rows)}; no repository checkout or model run")
        return 0
    if not args.instance:
        parser.error("--instance is required for prepare, inspect, or predict")
    if not INSTANCE_RE.fullmatch(args.instance):
        parser.error("Unsafe instance identifier")
    try:
        workspace = args.workspace_root.expanduser().resolve() / args.instance
        if args.command == "prepare":
            row = find_dev_row(args.instance)
            workspace = prepare_dev_instance(row, args.workspace_root)
            print(f"Prepared: {workspace}")
            print("Created ONLY public_task.json and issue.md; no gold patch, evaluator labels or tests")
            print("No repository code executed. Checked out exact historical base_commit.")
        elif args.command == "inspect":
            public = load_prepared(workspace)
            manifest, _ = external_manifest(
                public, model=args.model, max_steps=args.max_steps,
                proposal_reasoning_effort=args.proposal_reasoning_effort,
                file_inventory_limit=args.file_inventory_limit,
                proposal_reserve_tokens=args.proposal_reserve_tokens,
                behavioral_proposal=args.behavioral_proposal,
                tool_call_recovery=args.tool_call_recovery, matched_source=args.matched_source,
            )
            print(f"Prepared: {workspace}\nIssue: {public['instance_id']}\nRepository: {public['repo']}")
            print(f"Base commit: {public['base_commit']}\nMode: {manifest['conditions']} / host verification disabled")
        else:
            if (workspace / "episode.json").exists():
                raise BenchmarkAdapterError("Existing episode found. Use another workspace; no automatic overwriting")
            public = load_prepared(workspace)
            print(f"Running Qwen on {public['instance_id']} (real GitHub base commit)")
            print("WARNING: no host tests, no hidden grader input, no official score")
            record, prediction = run_local_pilot(
                workspace, model=args.model, max_steps=args.max_steps,
                proposal_reasoning_effort=args.proposal_reasoning_effort,
                file_inventory_limit=args.file_inventory_limit,
                proposal_reserve_tokens=args.proposal_reserve_tokens,
                behavioral_proposal=args.behavioral_proposal,
                tool_call_recovery=args.tool_call_recovery, matched_source=args.matched_source,
            )
            print(f"Agent status: {record['outcome']['status']}")
            if record["error"]:
                print(f"Agent error: {record['error']}")
            for attempt in record["proposal_attempts"]:
                print(f"Proposal {attempt['attempt']}: finish={attempt['finish_reason']}, "
                      f"visible_chars={attempt['response_chars']}, "
                      f"tokens={attempt['completion_tokens']}/{attempt['requested_max_tokens']}, "
                      f"reasoning_reported={attempt['reasoning_output_present']}")
            print(f"Observed: {record['observed_paths']}")
            print(f"Model calls: {record['usage']['model_calls']}, tokens: {record['usage']['total_tokens']}")
            print(f"Episode: {workspace / 'episode.json'}")
            print(f"SWE-bench prediction: {prediction if prediction else 'NOT EXPORTED (see episode / export error)'}")
            print("Only official Docker evaluation can assign resolved/unresolved.")
        return 0
    except (BenchmarkAdapterError, OSError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
