"""Observational trajectory audit of completed context-intervention runs.

This module analyzes *visible* actions and evidence exposure, not hidden model
reasoning or attention. Oracle paths are used only after runs for auditing.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def trajectory_signature(record: dict) -> str:
    """Hash semantic actions and patch decisions, excluding timestamps/token totals.

    Equal hashes across repeats imply identical *recorded decisions*, not
    independent demonstrations of stochastic robustness.
    """
    actions = []
    for event in record.get("trajectory", []):
        kind = event.get("kind")
        if kind == "tool_call":
            actions.append({"kind": kind, "name": event.get("name"),
                            "arguments": event.get("arguments"),
                            "valid": event.get("valid"),
                            "repeated_read": event.get("repeated_read")})
        elif kind == "patch_proposal":
            actions.append({"kind": kind, "path": event.get("path"),
                            "old": event.get("old"), "new": event.get("new")})
        elif kind == "protocol_error":
            actions.append({"kind": kind, "message": event.get("message")})
    return _digest({"actions": actions, "status": record.get("outcome", {}).get("status")})


def audit_record(record: dict, oracle_paths: list[str],
                 misleading_paths: list[str] | None = None) -> dict:
    """Summarize oracle exposure and off-target reads for a single run."""
    oracle = set(oracle_paths)
    misleading = set(misleading_paths or [])
    seeded = [item["path"] for item in record.get("intervention", {}).get("sources", [])]
    reads = [e for e in record.get("trajectory", [])
             if e.get("kind") == "tool_call" and e.get("name") == "read_file"]
    valid_reads = [e for e in reads if e.get("valid") is True]
    oracle_reads = [e for e in valid_reads if e.get("arguments", {}).get("path") in oracle]
    off_target = [e for e in valid_reads if e.get("arguments", {}).get("path") not in oracle]
    first_read = valid_reads[0].get("arguments", {}).get("path") if valid_reads else None
    patch = record.get("proposal") or {}
    return {
        "run_id": record["run_id"], "task_id": record["task_id"],
        "condition": record["condition"], "repetition": record["repetition"],
        "seeded_oracle": bool(oracle.intersection(seeded)),
        "seeded_misleading": bool(misleading.intersection(seeded)),
        "seeded_paths": seeded,
        "first_read_path": first_read,
        "first_read_is_oracle": first_read in oracle if first_read is not None else None,
        "oracle_observed": bool(oracle.intersection(seeded) or oracle_reads),
        "oracle_tool_reads": len(oracle_reads),
        "off_target_reads": len(off_target),
        "repeat_reads": sum(e.get("repeated_read") is True for e in reads),
        "read_expansions": sum(e.get("expanded_from_seed") is True for e in reads),
        "patch_in_oracle_file": patch.get("path") in oracle if patch else None,
        "patch_in_misleading_file": patch.get("path") in misleading if patch else None,
        "verified": record.get("outcome", {}).get("repair_verified") is True,
        "trajectory_signature": trajectory_signature(record),
    }


def audit_experiment(records: list[dict], manifest: dict) -> dict:
    oracle_by_task = {task["task_id"]: task["oracle"]["paths"]
                      for task in manifest["tasks"]}
    misleading_by_task = {task["task_id"]: task.get("misleading_pool", [])
                          for task in manifest["tasks"]}
    if len(oracle_by_task) != len(manifest["tasks"]):
        raise ValueError("Duplicate task IDs in manifest")
    signatures = defaultdict(list)
    rows = []
    seen = set()
    for record in records:
        if record.get("experiment_id") != manifest["experiment_id"]:
            raise ValueError("Run does not belong to this experiment")
        task_id = record["task_id"]
        if task_id not in oracle_by_task:
            raise ValueError(f"Unknown task in run records: {task_id}")
        key = (task_id, record["condition"], record["repetition"])
        if key in seen:
            raise ValueError(f"Duplicate task-condition-repetition: {key}")
        seen.add(key)
        item = audit_record(record, oracle_by_task[task_id],
                            misleading_by_task[task_id])
        rows.append(item)
        signatures[(task_id, record["condition"])].append(item["trajectory_signature"])
    by_condition = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(row)
    condition_summary = {}
    for condition, selected in sorted(by_condition.items()):
        condition_summary[condition] = {
            "runs": len(selected),
            "seeded_oracle": sum(item["seeded_oracle"] for item in selected),
            "seeded_misleading": sum(item["seeded_misleading"] for item in selected),
            "wrong_locus_patches": sum(item["patch_in_misleading_file"] is True for item in selected),
            "oracle_observed": sum(item["oracle_observed"] for item in selected),
            "off_target_reads": sum(item["off_target_reads"] for item in selected),
            "repeated_reads": sum(item["repeat_reads"] for item in selected),
            "read_expansions": sum(item["read_expansions"] for item in selected),
            "verified_repairs": sum(item["verified"] for item in selected),
        }
    same_trajectory_groups = []
    for (task_id, condition), hashes in sorted(signatures.items()):
        if len(hashes) > 1 and len(set(hashes)) == 1:
            same_trajectory_groups.append({"task_id": task_id,
                                           "condition": condition,
                                           "repetitions": len(hashes)})
    return {"experiment_id": manifest["experiment_id"],
            "total_runs": len(rows), "conditions": condition_summary,
            "identical_repeat_groups": same_trajectory_groups, "runs": rows}
