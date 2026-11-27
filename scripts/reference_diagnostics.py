"""Evaluator-only annotations for a completed paired development report."""
import json
from pathlib import Path

from patchscope.evaluation_git import apply_to_index, git, grader_patch_matches, temporary_patch_index
from patchscope.swebench_dev import INSTANCE_RE, SHA_RE, load_prepared


def read(path):
    return json.loads(path.read_bytes())


def test_group(case, key):
    group = (case.get("tests_status") or {}).get(key)
    if group is None:
        return None
    result = {}
    for field in ("success", "failure"):
        tests = group.get(field)
        if not isinstance(tests, list) or any(not isinstance(t, str) or not t for t in tests):
            raise ValueError(f"Malformed {key}.{field} test list")
        if len(tests) != len(set(tests)):
            raise ValueError(f"Duplicate tests in {key}.{field}")
        result[field] = sorted(tests)
    if set(result["success"]) & set(result["failure"]):
        raise ValueError(f"Conflicting test outcomes in {key}")
    return result


def control_inputs(entries, issues):
    controls = {}
    for base, file, report in entries:
        pred = read(Path(file))
        issue = pred["instance_id"]
        if (not INSTANCE_RE.fullmatch(issue) or issue not in issues or issue in controls
                or not SHA_RE.fullmatch(base) or not isinstance(pred["model_patch"], str)
                or not pred["model_patch"].strip()):
            raise ValueError("Invalid or duplicate reference control")
        report = Path(report).resolve()
        case = read(report)[issue]
        if case.get("patch_successfully_applied") is not True or type(case.get("resolved")) is not bool:
            raise ValueError(f"{report}: incomplete reference grade")
        if report.parent.name != issue or report.parent.parent.name != pred["model_name_or_path"].replace("/", "__"):
            raise ValueError(f"{report}: reference prediction and grader folder disagree")
        controls[issue] = (base.lower(), pred, report, case)
    return controls


def tree_ids(repo, base, patches):
    with temporary_patch_index(repo) as scratch:
        ids = []
        for patch in patches:
            apply_to_index(scratch, base, patch)
            ids.append(git(scratch, "write-tree").decode().strip())
    return ids


def annotate(report, arms, entries=()):
    controls = control_inputs(entries, {row["issue"] for row in report["issues"]})
    notes = []
    for row in report["issues"]:
        issue = row["issue"]
        for arm, (root, _, logs, _) in zip(("baseline", "candidate"), arms):
            if row[arm]["grade"] != "unresolved":
                continue
            note = {"issue": issue, "arm": arm, "official_grade": "unresolved",
                    "target": None, "existing": None, "reference": None}
            notes.append(note)
            path = logs / issue / "report.json" if logs else None
            if not path or not path.is_file():
                continue
            case = read(path)[issue]
            if case.get("resolved") is not False:
                raise ValueError(f"{path}: unresolved aggregate conflicts with per-issue report")
            note.update(target=test_group(case, "FAIL_TO_PASS"), existing=test_group(case, "PASS_TO_PASS"))
            if issue not in controls:
                continue
            base, reference, ref_report, ref_case = controls[issue]
            if path.resolve() == ref_report or path.resolve().parents[2] == ref_report.parents[2]:
                raise ValueError("Reference must come from a separate grader run")
            folder = root / issue
            pred = read(folder / "prediction.jsonl")
            public = load_prepared(folder)
            episode = read(folder / "episode.json")
            if (public["instance_id"] != issue or public["base_commit"].lower() != base
                    or episode["provenance"]["base_commit"].lower() != base):
                raise ValueError(f"{issue}: reference control base mismatch")
            model_tree, reference_tree = tree_ids(folder / "repo", base, [pred["model_patch"], reference["model_patch"]])
            ref_target = test_group(ref_case, "FAIL_TO_PASS")
            ref_existing = test_group(ref_case, "PASS_TO_PASS")
            ref_bound = grader_patch_matches(ref_report.parent, reference["model_patch"])
            model_bound = grader_patch_matches(path.parent, pred["model_patch"])
            note["reference"] = {
                "base": base, "model_tree": model_tree, "reference_tree": reference_tree,
                "resolved": ref_case["resolved"], "reference_run": ref_report.parents[2].name,
                "both_grader_patches_verified": model_bound and ref_bound,
                "target": ref_target, "existing": ref_existing,
                "same_failing_existing_tests": (note["existing"]["failure"] == ref_existing["failure"]
                                                if note["existing"] is not None and ref_existing is not None else None),
            }
    report["unresolved_diagnostics"] = notes


def group_text(group):
    if group is None:
        return "outcomes unavailable"
    return f"{len(group['success'])} passed, {len(group['failure'])} failed"


def format_diagnostics(notes):
    lines = ["", "## Unresolved prediction diagnostics", ""]
    if not notes:
        return lines + ["No officially unresolved predictions."]
    for n in notes:
        lines.extend([f"### {n['issue']} · {n['arm']}", "",
                      f"Official grade **unresolved**. Target tests: {group_text(n['target'])}. "
                      f"Existing tests: {group_text(n['existing'])}.", ""])
        for label, group in (("Target test failure", n["target"]), ("Existing test failure", n["existing"])):
            if group:
                lines.extend(f"- {label}: `{test}`" for test in group["failure"])
        r = n["reference"]
        if r:
            match = "identical" if r["model_tree"] == r["reference_tree"] else "different"
            grade = "resolved" if r["resolved"] else "unresolved"
            lines.extend(["", f"Reference run `{r['reference_run']}`: **{grade}**. Model and reference trees: **{match}**.",
                          f"Reference target tests: {group_text(r['target'])}. "
                          f"Reference existing tests: {group_text(r['existing'])}."])
            if r["existing"]:
                lines.extend(f"- Reference existing test failure: `{t}`" for t in r["existing"]["failure"])
            if not r["both_grader_patches_verified"]:
                lines.append("At least one grader patch.diff was unavailable for comparison with the submitted diff.")
        else:
            lines.append("Reference comparison unavailable.")
        lines.append("")
    return lines
