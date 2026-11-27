import json
from pathlib import Path
import subprocess
import sys

from scripts.demo_export_replay import prepare_fixture, saved_episode
from scripts.replay_export import replay


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def save_grade(tmp_path, name, task, prediction, patch, grade):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "patch.diff").write_text(patch, encoding="utf-8")
    write_json(folder / "report.json", {task: grade})
    return {"grader": str(folder), "prediction": prediction}


def test_archive_report_preserves_grades_and_separates_controls(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    base = prepare_fixture(repo)
    episode = saved_episode(base, "    return (a + b) / 2")
    task = episode["task_id"]
    original = episode["proposal_diff"]
    corrected, _ = replay(repo, episode, original.encode("utf-8"))
    broken_episode = write_json(tmp_path / "broken.json", episode)
    applied_episode = write_json(tmp_path / "applied.json", {**episode, "proposal_diff": corrected})
    prediction = write_json(tmp_path / "prediction.jsonl", {
        "instance_id": task, "model_patch": corrected,
    })
    grade = {
        "resolved": False,
        "patch_successfully_applied": True,
        "tests_status": {
            "FAIL_TO_PASS": {"success": ["test_average"], "failure": []},
            "PASS_TO_PASS": {"success": [], "failure": ["test_existing"]},
        },
    }
    model = save_grade(tmp_path, "model", task, prediction, corrected, grade)
    reference = save_grade(tmp_path, "reference", task, prediction, corrected, grade)
    mismatch = save_grade(tmp_path, "mismatched", task, prediction, original, grade)
    case = {"task_id": task, "repo": str(repo), "episode": broken_episode, "official_grade": "no_prediction"}
    manifest = write_json(tmp_path / "manifest.json", {"cases": [
        {**case, "id": "export", "group": "anchor"},
        {**case, **model, "id": "shared", "group": "archive", "official_grade": "unresolved",
         "episode": applied_episode, "reference": {**reference, "base_commit": base}},
        {**case, **model, "id": "no-control", "group": "archive", "official_grade": "unresolved",
         "episode": applied_episode},
        {**case, "id": "missing", "group": "control", "repo": str(tmp_path / "missing")},
        {**case, **mismatch, "id": "mismatch", "group": "control", "official_grade": "unresolved"},
    ]})
    result = subprocess.run(
        [sys.executable, "-m", "scripts.report_archive_diagnostics", "--manifest", manifest],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True,
    )
    assert str(tmp_path) not in result.stdout
    report = json.loads(result.stdout)
    rows = {row["id"]: row for row in report["cases"]}

    assert rows["export"]["official_grade"] == "no_prediction"
    assert rows["export"]["diagnostic_action"] == "retry_export"
    export = rows["export"]["checks"][0]["evidence"]
    assert export["original_git_rejection"] == "corrupt_patch"
    assert export["corrected_tree"] == export["intended_tree"]
    assert export["new_model_calls"] == 0

    assert rows["shared"]["official_grade"] == "unresolved"
    assert rows["shared"]["diagnostic_action"] == "investigate_shared_test_failure"
    shared = rows["shared"]["checks"][2]["evidence"]
    assert shared["model_tree"] == shared["reference_tree"]
    assert shared["archived_reference_resolved"] is False
    assert shared["both_target_test_groups_passed"] is True
    assert shared["shared_existing_test_failures"] == ["test_existing"]
    assert shared["underlying_cause"] == "undetermined"
    assert rows["no-control"]["action_changed"] is False

    assert rows["missing"]["missing_artifacts"] == ["repo"]
    assert rows["missing"]["action_changed"] is False
    assert rows["mismatch"]["official_grade"] == "unresolved"
    assert rows["mismatch"]["diagnostic_action"] == "verify_archive_consistency"
    assert rows["mismatch"]["checks"][1]["status"] == "mismatch"
    assert all(check["elapsed_ms"] >= 0 for row in rows.values() for check in row["checks"])
    archive = report["summary"]["groups"]["archive"]
    assert (archive["assigned"], archive["action_changes"], archive["action_change_fraction"]) == (2, 1, 0.5)
