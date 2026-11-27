"""Compare saved PatchScope development runs without model calls."""

import argparse
import hashlib
from collections import Counter
import json
import math
from pathlib import Path
import re
from statistics import median

from patchscope.evaluation_git import grader_patch_matches
from patchscope.swebench_dev import INSTANCE_RE


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def grade_index(summary):
    groups = {
        "resolved_ids": "resolved",
        "unresolved_ids": "unresolved",
        "error_ids": "grader_error",
        "ambiguous_failure_ids": "ambiguous",
        "infra_failure_ids": "infrastructure_failure",
    }
    grades = {}
    for key, status in groups.items():
        ids = summary.get(key, [])
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise ValueError(f"{key} must be a list of issue IDs")
        if len(set(ids)) != len(ids):
            raise ValueError(f"{key} contains duplicate issue IDs")
        for issue in ids:
            previous = grades.get(issue)
            if previous == "resolved":
                raise ValueError(f"Conflicting official result for {issue}")
            grades[issue] = status
    return grades


def metric(usage, key):
    value = usage.get(key)
    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
        return value
    return None


def read_issue(instance, root, grades, grader_root, submitted, *, editor_comparison=False):
    directory = root / instance
    episode_path = directory / "episode.json"
    prediction_path = directory / "prediction.jsonl"
    outcome = {"stage": "missing", "grade": "missing_episode", "applied": None,
               "tokens": None, "seconds": None}
    if not episode_path.is_file():
        if (prediction_path.exists() or instance in grades
                or (submitted is not None and instance in submitted)):
            raise ValueError(f"{episode_path}: missing episode for prediction or grade")
        return outcome, {}

    episode_bytes = episode_path.read_bytes()
    episode = json.loads(episode_bytes)
    if episode.get("task_id") != instance:
        raise ValueError(f"{episode_path}: task_id does not match {instance}")
    proposal = bool(episode.get("proposal"))
    exported = prediction_path.is_file()
    if exported:
        prediction = read_json(prediction_path)  # This adapter writes exactly one JSONL record.
        if (not proposal or prediction.get("instance_id") != instance
                or not episode.get("proposal_diff")
                or not isinstance(prediction.get("model_patch"), str)
                or prediction.get("model_patch") != episode["proposal_diff"]):
            raise ValueError(f"{prediction_path}: prediction does not match its saved proposal")
    elif instance in grades or (submitted is not None and instance in submitted):
        raise ValueError(f"{prediction_path}: grader references an issue without a prediction")
    if exported and instance in grades and submitted is not None and instance not in submitted:
        raise ValueError(f"{instance}: official grade is absent from the submitted IDs")

    status = episode.get("outcome", {}).get("status")
    error = episode.get("error")
    stage = "exported" if exported else "proposal_only" if proposal else "no_proposal"
    grade = grades.get(instance, "ungraded") if exported else "no_prediction"
    applied = False if not exported else None
    if grader_root is not None:
        report_path = grader_root / instance / "report.json"
        if report_path.is_file():
            case = read_json(report_path)[instance]
            if not exported:
                raise ValueError(f"{report_path}: official report without an exported prediction")
            grader_patch_matches(report_path.parent, prediction["model_patch"])
            value = case.get("patch_successfully_applied")
            if type(value) is bool:
                applied = value
            if grade == "resolved" and (applied is False or case.get("resolved") is False):
                raise ValueError(f"{report_path}: inconsistent official resolution")
            if grade == "unresolved" and case.get("resolved") is True:
                raise ValueError(f"{report_path}: inconsistent official resolution")
    usage = episode.get("usage", {})
    outcome.update(stage=stage, status=status, grade=grade, applied=applied,
                   tokens=metric(usage, "total_tokens"), seconds=metric(usage, "wall_seconds"))
    navigation_events = {event.get("kind") for event in episode.get("trajectory", [])}
    outcome["navigation"] = [
        label for event, label in (
            ("ranged_read_feedback", "ranged_read_feedback_episodes"),
            ("ranged_read_recovered", "ranged_read_recovered_episodes"),
        ) if event in navigation_events
    ]
    if not exported:
        # A controlled identifier is safe to include in a public summary.
        outcome["failure"] = (
            "export_rejected" if (directory / "prediction_export_error.txt").is_file()
            else next(iter(re.findall(
                r"^(?:ProposalContractError|ValueError): ((?:patch|python|removed|soft)_[a-z0-9_]+)\b",
                error or "")), status or "unknown")
        )
    provenance = episode.get("provenance", {})
    match = {key: provenance.get(key) for key in
             ("benchmark", "split", "base_commit", "public_issue_sha256", "generation")}
    recovery = episode.get("tool_call_recovery", False)
    if type(recovery) is not bool:
        raise ValueError(f"{episode_path}: tool_call_recovery must be boolean")
    match.update(budgets=episode.get("budgets"), condition=episode.get("condition"),
                 tool_call_recovery="on" if recovery else "off")
    if editor_comparison:
        editor = episode.get("editor_comparator")
        match["model"] = (match.pop("generation") or {}).get("model")
        match.pop("budgets")
        match["editor"] = None if editor is None else editor.get("name")
        if episode.get("matched_source") is True:
            snapshot = episode.get("proposal_source") or {}
            match["proposal_source"] = snapshot.get("sha256")
            if "proposal_windows" in episode:
                outcome["source_policy"] = "replayed_windows_v1"
            elif snapshot:
                outcome["source_policy"] = snapshot.get("policy", "complete_files")
        match["episode_sha256"] = hashlib.sha256(episode_bytes).hexdigest()
        match["parent_episode_sha256"] = None if editor is None else editor.get("baseline_episode_sha256")
    return outcome, match


def resolved(grade):
    return {"resolved": True, "unresolved": False, "no_prediction": False}.get(grade)


def summarize(rows, arm):
    outcomes = [row[arm] for row in rows]
    metrics = {}
    for key in ("tokens", "seconds"):
        known = [outcome[key] for outcome in outcomes if outcome[key] is not None]
        metrics[key] = {"recorded": len(known), "total": sum(known) if known else None,
                        "median": median(known) if known else None}
    return {
        "stages": dict(Counter(outcome["stage"] for outcome in outcomes)),
        "grades": dict(Counter(outcome["grade"] for outcome in outcomes)),
        "applied": sum(outcome["applied"] is True for outcome in outcomes),
        "application_unknown": sum(outcome["applied"] is None for outcome in outcomes),
        "generation_failures": dict(Counter(outcome["failure"] for outcome in outcomes
                                            if "failure" in outcome)),
        "navigation": dict(Counter(metric for outcome in outcomes
                                   for metric in outcome.get("navigation", []))),
        "usage": metrics,
    }


def compare(instances, baseline, candidate, *, tool_call_recovery_ablation=False,
            editor_comparison=False, matched_source_comparison=False):
    editor_comparison = editor_comparison or matched_source_comparison
    rows = []
    for instance in instances:
        before, left = read_issue(instance, *baseline, editor_comparison=editor_comparison)
        after, right = read_issue(instance, *candidate, editor_comparison=editor_comparison)
        editor_fields = {"editor", "episode_sha256", "parent_episode_sha256"}
        keys = left.keys() | right.keys()
        if editor_comparison:
            keys -= editor_fields
        differences = sorted(key for key in keys
                             if not left.get(key) or left.get(key) != right.get(key))
        if (tool_call_recovery_ablation
                and left.get("tool_call_recovery") == "off"
                and right.get("tool_call_recovery") == "on"):
            differences.remove("tool_call_recovery")
        elif tool_call_recovery_ablation and "tool_call_recovery" not in differences:
            differences.append("tool_call_recovery")
        if editor_comparison and (
            left.get("editor") is not None or right.get("editor") != "aider_diff"
            or left.get("episode_sha256") != right.get("parent_episode_sha256")
        ):
            differences.append("editor_comparison_link")
        if matched_source_comparison and not (left.get("proposal_source") and right.get("proposal_source")):
            if "proposal_source" not in differences:
                differences.append("proposal_source")
        comparable = bool(left and right and not differences)
        old, new = resolved(before["grade"]), resolved(after["grade"])
        change = None
        if comparable and old is not None and new is not None:
            change = "unchanged" if old == new else "gain" if new else "loss"
        rows.append({"issue": instance, "baseline": before, "candidate": after,
                     "matched_metadata": comparable, "metadata_differences": differences,
                     "resolution_change": change})
    return {
        "assigned": len(rows),
        "editor_comparison": editor_comparison,
        "matched_source_comparison": matched_source_comparison,
        "tool_call_recovery_ablation": tool_call_recovery_ablation,
        "baseline": summarize(rows, "baseline"),
        "candidate": summarize(rows, "candidate"),
        "matched_metadata": sum(row["matched_metadata"] for row in rows),
        "paired_resolution": dict(Counter(row["resolution_change"] or "unavailable"
                                          for row in rows)),
        "issues": rows,
    }


def markdown(report):
    lines = ["# PatchScope paired development report", "",
             f"Assigned issues **{report['assigned']}**. "
             f"Pairs with matching recorded settings **{report['matched_metadata']}**.", "",
             "The official grader supplies the resolution result. "
             "Successful export records a preflight applicability check. "
             "The applied count uses per-issue grader reports when available.", "",
             "| Metric | Baseline | Candidate |", "|---|---:|---:|"]
    if report.get("editor_comparison"):
        match_label = ("Linked pairs with matching issue, base, model and source snapshot"
                       if report.get("matched_source_comparison")
                       else "Linked pairs with matching issue, base and model")
        lines[2] = (f"Assigned issues **{report['assigned']}**. "
                    f"{match_label} **{report['matched_metadata']}**.")
        replayed = any(row["baseline"].get("source_policy") == "replayed_windows_v1"
                       for row in report["issues"])
        if replayed:
            evidence = ("Both editors receive the same bounded source excerpts from saved exploration. "
                        "Native and candidate time cover their editing passes. ")
        elif report.get("matched_source_comparison"):
            evidence = "Both editors receive the same complete selected source files. "
        else:
            evidence = "The Aider pass uses complete files selected by PatchScope's exploration. "
        lines[4:4] = [
            evidence + "Prompts, edit formats and budgets differ."
            + ("" if replayed else " Candidate time covers only the Aider pass."),
            "",
        ]
    if report.get("tool_call_recovery_ablation"):
        lines[3:3] = ["Declared intervention: tool-call recovery off vs. on.", ""]
    before, after = report["baseline"], report["candidate"]
    for group in ("stages", "grades", "generation_failures", "navigation"):
        for key in sorted(before[group].keys() | after[group].keys()):
            lines.append(f"| {key} | {before[group].get(key, 0)} | {after[group].get(key, 0)} |")
    for key in ("applied", "application_unknown"):
        lines.append(f"| {key} | {before[key]} | {after[key]} |")
    for key in ("tokens", "seconds"):
        values = [arm["usage"][key] for arm in (before, after)]
        left, right = [f"{value['total']} ({value['recorded']}/{report['assigned']} recorded)"
                       if value["total"] is not None else "Unavailable" for value in values]
        lines.append(f"| Total {key} | {left} | {right} |")
    gains = report["paired_resolution"].get("gain", 0)
    losses = report["paired_resolution"].get("loss", 0)
    unavailable = report["paired_resolution"].get("unavailable", 0)
    lines += ["", f"Paired resolution changes **{gains} gains**, **{losses} losses**, "
              f"**{unavailable} unavailable**.", "",
              "| Issue | Baseline export / grade | Candidate export / grade | Resolution change |",
              "|---|---|---|---|"]
    for row in report["issues"]:
        old, new = row["baseline"], row["candidate"]
        lines.append(f"| {row['issue']} | {old['stage']} / {old['grade']} | "
                     f"{new['stage']} / {new['grade']} | {row['resolution_change'] or '—'} |")
    if "unresolved_diagnostics" in report:
        from scripts.reference_diagnostics import format_diagnostics
        lines.extend(format_diagnostics(report["unresolved_diagnostics"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, required=True, help="One issue ID per line")
    for arm in ("baseline", "candidate"):
        parser.add_argument(f"--{arm}", type=Path, required=True, help="Episode directory")
        parser.add_argument(f"--{arm}-grader", type=Path, help="Official aggregate JSON")
        parser.add_argument(f"--{arm}-grader-root", type=Path, help="Parent of issue report directories")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--diagnose-unresolved", action="store_true", help="Show official target and existing test outcomes")
    parser.add_argument("--reference-control", nargs=3, action="append", default=[],
                        metavar=("BASE", "REFERENCE_JSONL", "REFERENCE_REPORT"),
                        help="Compare one separately graded reference prediction on its pinned base")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--editor-comparison", action="store_true",
                      help="Compare native episodes with linked Aider passes")
    mode.add_argument("--matched-source-comparison", action="store_true",
                      help="Require a matching source snapshot for each editor pair")
    mode.add_argument("--tool-call-recovery-ablation", action="store_true",
                        help="Require recovery off in baseline and on in candidate")
    args = parser.parse_args(argv)
    try:
        instances = args.instances.read_text(encoding="utf-8").split()
        if (not instances or not all(INSTANCE_RE.fullmatch(issue) for issue in instances)
                or len(set(instances)) != len(instances)):
            raise ValueError("Provide unique, valid issue IDs")
        arms = []
        for name in ("baseline", "candidate"):
            root = getattr(args, name)
            if not root.is_dir():
                raise ValueError(f"{root}: episode directory does not exist")
            summary_path = getattr(args, f"{name}_grader")
            summary = read_json(summary_path) if summary_path else {}
            submitted = summary.get("submitted_ids")
            if submitted is not None and (
                not isinstance(submitted, list) or not all(isinstance(item, str) for item in submitted)
            ):
                raise ValueError(f"{summary_path}: submitted_ids must be a list of issue IDs")
            arms.append((root, grade_index(summary), getattr(args, f"{name}_grader_root"),
                         set(submitted) if submitted is not None else None))
        report = compare(instances, *arms,
                         tool_call_recovery_ablation=args.tool_call_recovery_ablation,
                         editor_comparison=args.editor_comparison,
                         matched_source_comparison=args.matched_source_comparison)
        if args.diagnose_unresolved or args.reference_control:
            from scripts.reference_diagnostics import annotate
            annotate(report, arms, args.reference_control)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(json.dumps(report, indent=2) if args.format == "json" else markdown(report), end="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
