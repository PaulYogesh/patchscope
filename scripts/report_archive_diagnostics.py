"""Report a fixed set of checks over saved coding-agent runs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from time import perf_counter

from patchscope.evaluation_git import grader_patch_matches
from patchscope.swebench_dev import SHA_RE
from scripts.reference_diagnostics import test_group, tree_ids
from scripts.replay_export import read_json, replay, verify_expected_replay


GRADE_ACTIONS = {
    "resolved": "accept_official_result",
    "unresolved": "inspect_unresolved_run",
    "grader_error": "inspect_grader_error",
    "infrastructure_failure": "inspect_grader_error",
    "ambiguous": "inspect_unresolved_run",
    "no_prediction": "inspect_missing_prediction",
    "ungraded": "collect_grade",
    "unknown": "collect_grade",
}
GROUPS = ("anchor", "archive", "control")


class EvidenceIssue(ValueError):
    def __init__(self, status, detail, missing=()):
        super().__init__(detail)
        self.status = status
        self.missing = missing


def path_for(inputs, role):
    value = inputs.get(role)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{role} must be a nonempty path string")
    return Path(value).expanduser() if value is not None else None


def require_artifacts(**paths):
    missing = [role for role, path in paths.items() if path is None or not path.exists()]
    if missing:
        raise EvidenceIssue("missing", "Required artifacts are unavailable", missing)


def timed_check(name, operation, *args):
    started = perf_counter()
    result = {"name": name, "status": "verified"}
    inputs = None
    try:
        result["evidence"], inputs = operation(*args)
    except EvidenceIssue as error:
        result.update(status=error.status, detail=str(error))
        if error.missing:
            result["missing_artifacts"] = list(error.missing)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # Raw Git and file errors can contain private paths or patch text.
        result.update(status="error", detail=type(error).__name__)
    result["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
    return result, inputs


def read_episode(case, path):
    episode = read_json(path)
    if episode["task_id"] != case["task_id"]:
        raise EvidenceIssue("mismatch", "Episode belongs to a different task")
    return episode


def check_replay(case):
    repo, episode_path = (path_for(case, role) for role in ("repo", "episode"))
    require_artifacts(episode=episode_path)
    episode = read_episode(case, episode_path)
    proposal = episode.get("proposal")
    if not isinstance(proposal, dict) or not {
        "path", "start_line", "end_line", "expected_sha256", "replacement",
    }.issubset(proposal):
        raise EvidenceIssue("missing", "No saved line-range edit", ("line_range_proposal",))
    original = episode.get("proposal_diff")
    if not isinstance(original, str) or not original.strip():
        raise EvidenceIssue("missing", "No saved original diff", ("original_diff",))
    require_artifacts(repo=repo)
    _, replayed = replay(repo, episode, original.encode("utf-8"))
    if "expected_replay" in episode:
        try:
            verify_expected_replay(episode["expected_replay"], replayed)
        except ValueError as error:
            raise EvidenceIssue("mismatch", str(error)) from error
    rejection = replayed["original_git_rejection"]
    evidence = {key: replayed[key] for key in (
        "base_commit", "original_patch_sha256", "original_tree", "intended_tree", "corrected_tree",
        "corrected_patch_sha256", "legacy_renderer_reproduces_original_bytes", "new_model_calls",
    )}
    evidence["original_git_rejection"] = (
        "corrupt_patch" if "corrupt patch" in (rejection or "").casefold()
        else "other" if rejection else None
    )
    if "expected_replay" in episode:
        evidence["expected_replay_verified"] = True
    if "archived_grader_result" in episode:
        archived = episode["archived_grader_result"]
        if (archived["patch_sha256"] != evidence["corrected_patch_sha256"]
                or archived["patch_successfully_applied"] is not True
                or type(archived["official_resolved"]) is not bool):
            raise EvidenceIssue("mismatch", "Recorded recovered grade differs from the corrected replay")
        evidence["recorded_recovered_grade"] = (
            "resolved" if archived["official_resolved"] else "unresolved"
        )
    return evidence, None


def check_grader(inputs, task_id, official_grade=None, *, prefix=""):
    prediction_path = path_for(inputs, "prediction")
    grader = path_for(inputs, "grader")
    report_path = grader / "report.json" if grader is not None else None
    patch_path = grader / "patch.diff" if grader is not None else None
    require_artifacts(**{prefix + role: path for role, path in (
        ("prediction", prediction_path), ("grader_report", report_path), ("grader_patch", patch_path),
    )})
    prediction = read_json(prediction_path)
    if prediction["instance_id"] != task_id:
        raise EvidenceIssue("mismatch", "Prediction belongs to a different task")
    patch = prediction["model_patch"]
    if not isinstance(patch, str) or not patch.strip():
        raise ValueError("Invalid prediction patch")
    report = read_json(report_path)
    if task_id not in report:
        raise EvidenceIssue("mismatch", "Grader report has no entry for the task")
    grade = report[task_id]
    try:
        matched = grader_patch_matches(grader, patch)
    except ValueError as error:
        raise EvidenceIssue("mismatch", "Grader patch differs from the submitted prediction") from error
    if not matched:
        raise EvidenceIssue("missing", "Grader patch is unavailable", (prefix + "grader_patch",))
    resolved = grade.get("resolved")
    applied = grade.get("patch_successfully_applied")
    if type(resolved) is not bool or type(applied) is not bool:
        raise EvidenceIssue("missing", "Grader outcome fields are absent", (prefix + "grader_outcome",))
    if (resolved and not applied
            or official_grade == "no_prediction"
            or official_grade == "resolved" and not resolved
            or official_grade == "unresolved" and resolved):
        raise EvidenceIssue("mismatch", "Grader outcome conflicts with the recorded result")
    evidence = {
        "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        "archived_resolved": resolved,
        "patch_successfully_applied": applied,
    }
    return evidence, (patch, grade, report_path.resolve())


def check_reference(case, model):
    if model is None:
        raise EvidenceIssue("skipped", "Requires verified model grader binding")
    model_patch, model_grade, model_report = model
    if model_grade["patch_successfully_applied"] is not True or model_grade["resolved"] is not False:
        raise EvidenceIssue("skipped", "Requires an unresolved, applied model prediction")
    _, (reference_patch, reference_grade, reference_report) = check_grader(
        case["reference"], case["task_id"], prefix="reference_",
    )
    if model_report == reference_report:
        raise EvidenceIssue("mismatch", "Model and reference use the same grader report")
    if reference_grade["patch_successfully_applied"] is not True:
        raise EvidenceIssue("skipped", "Reference patch did not apply in its archived grader run")

    repo, episode_path = (path_for(case, role) for role in ("repo", "episode"))
    require_artifacts(repo=repo, episode=episode_path)
    base = read_episode(case, episode_path)["provenance"]["base_commit"]
    if not SHA_RE.fullmatch(base) or base != case["reference"].get("base_commit"):
        raise EvidenceIssue("mismatch", "Model and reference base commits differ or are invalid")
    model_tree, reference_tree = tree_ids(repo, base, [model_patch, reference_patch])
    model_target = test_group(model_grade, "FAIL_TO_PASS")
    ref_target = test_group(reference_grade, "FAIL_TO_PASS")
    model_existing = test_group(model_grade, "PASS_TO_PASS")
    ref_existing = test_group(reference_grade, "PASS_TO_PASS")
    evidence = {
        "base_commit": base,
        "model_tree": model_tree,
        "reference_tree": reference_tree,
        "archived_reference_resolved": reference_grade["resolved"],
        "underlying_cause": "undetermined",
        "both_target_test_groups_passed": bool(
            model_target and ref_target and model_target["success"]
            and model_target["success"] == ref_target["success"]
            and not model_target["failure"] and not ref_target["failure"]
        ),
        "shared_existing_test_failures": (
            sorted(set(model_existing["failure"]) & set(ref_existing["failure"]))
            if model_existing is not None and ref_existing is not None else None
        ),
        "same_failing_existing_tests": (
            model_existing["failure"] == ref_existing["failure"]
            if model_existing is not None and ref_existing is not None else None
        ),
    }
    missing = [role for role, group in (
        ("model_target_tests", model_target), ("reference_target_tests", ref_target),
        ("model_existing_tests", model_existing), ("reference_existing_tests", ref_existing),
    ) if group is None]
    if missing:
        evidence["unavailable_test_groups"] = missing
    return evidence, None


def diagnose(case):
    grade = case["official_grade"]
    replay_check, _ = timed_check("export_replay", check_replay, case)
    checks = [replay_check]
    model = None
    if grade != "no_prediction" or case.get("grader") is not None or case.get("prediction") is not None:
        grader_check, model = timed_check("grader_binding", check_grader, case, case["task_id"], grade)
        checks.append(grader_check)
    reference = {}
    if "reference" in case:
        reference_check, _ = timed_check("reference_control", check_reference, case, model)
        checks.append(reference_check)
        reference = reference_check.get("evidence", {})

    baseline = GRADE_ACTIONS[grade]
    action = baseline
    replayed = replay_check.get("evidence", {})
    if any(check["status"] == "mismatch" for check in checks):
        action = "verify_archive_consistency"
    elif (grade == "no_prediction" and replayed.get("original_git_rejection") == "corrupt_patch"
          and replayed["legacy_renderer_reproduces_original_bytes"]):
        action = "retry_export"
    elif (grade == "unresolved" and reference
          and reference["model_tree"] == reference["reference_tree"]
          and reference["archived_reference_resolved"] is False
          and reference["both_target_test_groups_passed"]
          and reference["same_failing_existing_tests"] and reference["shared_existing_test_failures"]):
        action = "investigate_shared_test_failure"
    missing = {role for check in checks for role in check.get("missing_artifacts", [])}
    missing.update(reference.get("unavailable_test_groups", []))
    return {
        "id": case["id"], "task_id": case["task_id"], "group": case["group"],
        "official_grade": grade, "grade_only_action": baseline, "diagnostic_action": action,
        "action_changed": action != baseline, "checks": checks, "missing_artifacts": sorted(missing),
    }


def build_report(manifest):
    cases = manifest["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("Expected a nonempty cases list")
    ids = set()
    for case in cases:
        if (not isinstance(case, dict)
                or any(not isinstance(case.get(key), str) or not case[key].strip()
                       for key in ("id", "task_id", "group", "official_grade"))
                or case["id"] in ids or case["group"] not in GROUPS
                or case["official_grade"] not in GRADE_ACTIONS
                or "reference" in case and not isinstance(case["reference"], dict)):
            raise ValueError("Invalid case metadata or duplicate case ID")
        ids.add(case["id"])
    rows = [diagnose(case) for case in cases]
    groups = {}
    for group in GROUPS:
        selected = [row for row in rows if row["group"] == group]
        changes = sum(row["action_changed"] for row in selected)
        groups[group] = {
            "assigned": len(selected), "action_changes": changes,
            "action_change_fraction": changes / len(selected) if selected else None,
            "cases_with_missing_artifacts": sum(bool(row["missing_artifacts"]) for row in selected),
            "cases_with_verified_checks": sum(
                any(check["status"] == "verified" for check in row["checks"]) for row in selected
            ),
        }
    checks = [check for row in rows for check in row["checks"]]
    return {
        "summary": {
            "groups": groups,
            "check_statuses": dict(Counter(check["status"] for check in checks)),
            "check_elapsed_ms": round(sum(check["elapsed_ms"] for check in checks), 3),
        },
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="JSON manifest of assigned cases")
    args = parser.parse_args()
    try:
        report = build_report(read_json(args.manifest.expanduser()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not read the batch manifest: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
