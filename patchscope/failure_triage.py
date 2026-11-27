"""Offline diagnosis for PatchScope experiment failures and repeated runs.

No LLM calls or test execution. It consumes only recorded run JSON. These
labels describe *observable pipeline stages*, not model cognition or causality.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from patchscope.trajectory_audit import trajectory_signature


REPAIR_VERIFIED = "resolved"


def failure_stage(record: dict) -> str:
    """Best observable stage at which a run stopped; not inferred intent."""
    status = record.get("outcome", {}).get("status", "missing_status")
    if status == REPAIR_VERIFIED:
        return "verified_repair"
    if status == "repair_failed_tests":
        return "patched_tests_failed"
    if status == "baseline_already_passes":
        return "baseline_already_passed"
    if status == "proposal_requires_explicit_verification_opt_in":
        return "verification_not_authorized"
    if status == "protocol_error":
        return "tool_protocol"

    events = record.get("trajectory", [])
    event_kinds = {e.get("kind") for e in events}
    if "test_execution" in event_kinds:
        return "test_execution_or_application"
    if "patch_proposal" in event_kinds or record.get("proposal"):
        return "post_proposal_pre_test"
    purposes = [e.get("purpose") for e in record.get("usage", {}).get("usage_events", [])]
    if "patch_proposal" in purposes:
        return "proposal_parsing_or_validation"
    if "exploration" in purposes:
        return "exploration_or_proposal_request"
    return "before_or_during_first_model_call"


def error_category(record: dict) -> str:
    """Categorize recorded error strings conservatively."""
    error = str(record.get("error") or "")
    status = record.get("outcome", {}).get("status", "missing_status")
    if not error:
        if status == "resolved":
            return "none"
        if status == "repair_failed_tests":
            return "patched_tests_failed"
        if status == "baseline_already_passes":
            return "baseline_already_passed"
        if status == "proposal_requires_explicit_verification_opt_in":
            return "verification_opt_out"
        return "unclassified_no_error_text"
    low = error.lower()
    if status == "protocol_error" or "toolprotocolerror" in low:
        return "tool_protocol"
    if any(term in low for term in ("budget_exhausted", "step_limit", "max_tool_calls")):
        return "resource_or_step_budget"
    if "no_source_code_observed" in low:
        return "no_code_observed"
    if "patch_json_invalid_or_missing" in low:
        return "patch_json_parsing"
    if any(term in low for term in (
        "patch_fields_", "patch_field_types_", "patch_edit_", "patch_path_",
        "patch_old_not_unique_",
        "patch_old_fragment", "patch_references_", "invalid_patch_",
        "non_string_patch_", "source_replacement", "old_fragment",
        "invalid_patch_proposal",
    )):
        return "patch_contract_validation"
    if any(term in low for term in ("jsondecodeerror", "invalid_json", "no json", "json object", "malformed json")):
        return "patch_json_parsing"
    if any(term in low for term in ("timeout", "timed out")):
        return "timeout"
    if any(term in low for term in ("connection", "network", "openaierror", "apiconnectionerror")):
        return "model_transport"
    return "other_recorded_exception"


def _short_error(record: dict, max_chars: int = 170) -> str:
    """Only a short diagnostic string, never full prompts, tools or source."""
    original = str(record.get("error") or "")
    return original[:max_chars] + ("…" if len(original) > max_chars else "")


def triage_records(records: list[dict], manifest: dict) -> dict[str, Any]:
    """Build a source-free, upload-safe summary of local experiment records."""
    expected_id = manifest["experiment_id"]
    expected_conditions = set(manifest["conditions"])
    expected_tasks = {task["task_id"] for task in manifest["tasks"]}
    expected_repetitions = manifest["repetitions"]
    seen = set()
    matrix: dict[tuple[str, str], list[dict]] = defaultdict(list)
    pairs: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for record in records:
        task, condition, rep = record["task_id"], record["condition"], record["repetition"]
        if record.get("experiment_id") != expected_id:
            raise ValueError("Record belongs to a different experiment")
        if task not in expected_tasks or condition not in expected_conditions:
            raise ValueError(f"Unexpected task/condition: {task}/{condition}")
        if type(rep) is not int or not (0 <= rep < expected_repetitions):
            raise ValueError(f"Unexpected repetition: {rep!r}")
        key = (task, condition, rep)
        if key in seen:
            raise ValueError(f"Duplicate run: {key}")
        seen.add(key)
        matrix[(task, condition)].append(record)
        pairs[(task, rep)][condition] = record

    by_task = []
    by_condition = defaultdict(lambda: {"runs": 0, "verified": 0, "status": Counter(), "errors": Counter()})
    representatives = []
    groups_identical = 0
    independent_signatures = set()
    for task in sorted(expected_tasks):
        row = {"task_id": task, "conditions": {}}
        for condition in manifest["conditions"]:
            group = sorted(matrix[(task, condition)], key=lambda r: r["repetition"])
            signatures = [trajectory_signature(r) for r in group]
            unique_count = len(set(signatures))
            if len(group) > 1 and unique_count == 1:
                groups_identical += 1
            statuses = Counter(r.get("outcome", {}).get("status", "missing_status") for r in group)
            errors = Counter(error_category(r) for r in group if not r.get("outcome", {}).get("repair_verified", False))
            verified = sum(r.get("outcome", {}).get("repair_verified") is True for r in group)
            row["conditions"][condition] = {
                "runs": len(group), "verified": verified,
                "statuses": dict(sorted(statuses.items())),
                "error_categories": dict(sorted(errors.items())),
                "unique_trajectory_signatures": unique_count,
            }
            c = by_condition[condition]
            c["runs"] += len(group)
            c["verified"] += verified
            c["status"].update(statuses)
            c["errors"].update(errors)
            for r, signature in zip(group, signatures):
                independent_signatures.add((task, condition, signature))
            # Retain a single representative for each task/condition/error/stage.
            seen_failure_keys = set()
            for r in group:
                if r.get("outcome", {}).get("repair_verified") is True:
                    continue
                stage = failure_stage(r)
                cat = error_category(r)
                status = r.get("outcome", {}).get("status", "missing_status")
                signature = (status, stage, cat, _short_error(r))
                if signature in seen_failure_keys:
                    continue
                seen_failure_keys.add(signature)
                reps = sum(
                    (other.get("outcome", {}).get("status", "missing_status"),
                     failure_stage(other), error_category(other), _short_error(other)) == signature
                    for other in group
                )
                representatives.append({
                    "run_id": r["run_id"], "task_id": task, "condition": condition,
                    "repetitions_with_same_diagnosis": reps,
                    "status": status, "failure_stage": stage, "error_category": cat,
                    "error": _short_error(r),
                    "last_events": [e.get("kind") for e in r.get("trajectory", [])[-3:]],
                    "proposal_present": r.get("proposal") is not None,
                    "baseline_passed": r.get("verification", {}).get("baseline_passed"),
                    "patched_passed": r.get("verification", {}).get("patched_passed"),
                })
        by_task.append(row)

    overlaps = []
    for (task, rep), members in sorted(pairs.items()):
        if "oracle" not in members or "bm25" not in members:
            continue
        bm25 = members["bm25"]
        oracle = members["oracle"]
        b = bm25.get("intervention", {})
        o = oracle.get("intervention", {})
        overlaps.append({
            "task_id": task, "repetition": rep,
            "same_seeded_paths": [x.get("path") for x in b.get("sources", [])] ==
                                 [x.get("path") for x in o.get("sources", [])],
            "same_seed_char_count": b.get("seed_chars") == o.get("seed_chars"),
            "same_trajectory": trajectory_signature(bm25) == trajectory_signature(oracle),
            "same_total_tokens": bm25.get("usage", {}).get("total_tokens") == oracle.get("usage", {}).get("total_tokens"),
        })

    return {
        "experiment_id": expected_id,
        "total_runs": len(records), "distinct_tasks": len({r["task_id"] for r in records}),
        "distinct_task_condition_trajectories": len(independent_signatures),
        "identical_repeat_groups": groups_identical,
        "total_task_condition_groups_with_multiple_runs": sum(len(group) > 1 for group in matrix.values()),
        "by_condition": {
            condition: {"runs": v["runs"], "verified": v["verified"],
                        "statuses": dict(sorted(v["status"].items())),
                        "error_categories": dict(sorted(v["errors"].items()))}
            for condition, v in sorted(by_condition.items())
        },
        "by_task": by_task,
        "failure_representatives": representatives,
        "bm25_oracle_pairs": overlaps,
    }


def render_triage(report: dict, *, manifest: dict) -> str:
    lines = [
        f"# PatchScope failure triage — {report['experiment_id']}", "",
        "This diagnostic reads existing JSON records only. It does **not** rerun the model, "
        "execute fixture code, or reveal hidden reasoning.", "",
        "## Effective diversity", "",
        f"- Recorded runs: **{report['total_runs']}**",
        f"- Distinct tasks: **{report['distinct_tasks']}**",
        f"- Distinct task–condition trajectory signatures: **{report['distinct_task_condition_trajectories']}**",
        f"- Identical-repetition groups: **{report['identical_repeat_groups']} / "
        f"{report['total_task_condition_groups_with_multiple_runs']}**", "",
        "Repeated identical trajectories do not provide independent behavioral variation. "
        "Do not interpret these run counts as an effective sample of independent tasks.", "",
        "## Outcomes by task and context", "",
        "| Task | " + " | ".join(manifest["conditions"]) + " |",
        "|---|" + "---:|" * len(manifest["conditions"]),
    ]
    for task in report["by_task"]:
        cols = []
        for condition in manifest["conditions"]:
            c = task["conditions"][condition]
            statuses = ", ".join(f"{name}×{n}" for name, n in c["statuses"].items()) or "none"
            cols.append(f"{c['verified']}/{c['runs']} ({statuses})")
        lines.append("| `" + task["task_id"] + "` | " + " | ".join(cols) + " |")
    lines += ["", "## Failure breakdown", "",
              "| Condition | Recorded runs | Verified | Failure categories |",
              "|---|---:|---:|---|"]
    for cond, v in report["by_condition"].items():
        errors = ", ".join(f"`{code}` {count}" for code, count in v["error_categories"].items()) or "—"
        lines.append(f"| {cond} | {v['runs']} | {v['verified']} | {errors} |")
    lines += ["", "## Representative unsuccessful records", "",
              "One example per distinct task/condition/failure signature. "
              "Error strings are shortened; no source transcripts are included.", "",
              "| Example run | Similar repetitions | Observed stopping stage | Category | Error |",
              "|---|---:|---|---|---|"]
    for r in report["failure_representatives"]:
        safe_error = r["error"].replace("|", "\\|").replace("\n", " ").replace("`", "'") or "—"
        lines.append(f"| `{r['run_id']}` | {r['repetitions_with_same_diagnosis']} | "
                     f"{r['failure_stage']} | `{r['error_category']}` | {safe_error} |")
    overlaps = report["bm25_oracle_pairs"]
    if overlaps:
        both = sum(x["same_seeded_paths"] and x["same_seed_char_count"] and
                   x["same_trajectory"] and x["same_total_tokens"] for x in overlaps)
        lines += ["", "## BM25–oracle diagnostic overlap", "",
                  f"{both}/{len(overlaps)} matched task–repetition pairs had identical seeded paths, "
                  "displayed character counts, recorded action signatures, and total tokens. "
                  "This is evidence of observationally overlapping interventions, **not** "
                  "proof that every prompt byte was identical.", ""]
    lines += ["## Next interpretation rule", "",
              "A run marked `error` is **not** automatically a demonstrated incorrect code repair. "
              "Classify its recorded exception and stopping stage first. "
              "A `repair_failed_tests` status has a distinct meaning: a patch was proposed, "
              "applied, and did not pass verification. Never convert all errors into patch failures.", "",
              "The empirical unit for a task-general conclusion is the distinct task. "
              "The pilot is instrumentation evidence, not a statistically powered result.", ""]
    return "\n".join(lines)
