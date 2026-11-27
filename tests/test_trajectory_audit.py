import copy

import pytest

from patchscope.trajectory_audit import audit_record, audit_experiment, trajectory_signature
from scripts.audit_experiment import render_markdown


def make_record(condition="native", repetition=0):
    return {"experiment_id": "audit-test", "run_id": f"t1__{condition}__r{repetition:02d}",
            "task_id": "t1", "condition": condition, "repetition": repetition,
            "intervention": {"sources": [{"path": "irrelevant.py"}] if condition == "placebo" else []},
            "trajectory": [
                {"kind": "model_response", "prompt_tokens": 100, "completion_tokens": 20},
                {"kind": "tool_call", "name": "read_file", "arguments": {"path": "irrelevant.py"},
                 "valid": True, "repeated_read": condition == "placebo"},
                {"kind": "tool_call", "name": "read_file", "arguments": {"path": "fix.py"},
                 "valid": True, "repeated_read": False},
                {"kind": "patch_proposal", "path": "fix.py", "old": "bug", "new": "fix"}],
            "proposal": {"path": "fix.py"},
            "outcome": {"status": "resolved", "repair_verified": True}}


def manifest():
    return {"experiment_id": "audit-test", "tasks": [{"task_id": "t1", "oracle": {"paths": ["fix.py"]}}]}


def test_audit_observation_and_orthogonal_diagnostic_metrics():
    row = audit_record(make_record("placebo"), ["fix.py"])
    assert row["oracle_observed"] is True
    assert row["seeded_oracle"] is False
    assert row["off_target_reads"] == 1
    assert row["repeat_reads"] == 1
    assert row["first_read_is_oracle"] is False
    assert row["patch_in_oracle_file"] is True


def test_signature_excludes_model_tokens_but_detects_decisions():
    first = make_record()
    same = copy.deepcopy(first)
    same["trajectory"][0]["prompt_tokens"] = 10000
    assert trajectory_signature(first) == trajectory_signature(same)
    same["trajectory"][1]["arguments"]["path"] = "different.py"
    assert trajectory_signature(first) != trajectory_signature(same)


def test_identical_repeated_decisions_flagged_not_claimed_independent():
    r0 = make_record()
    r1 = make_record(repetition=1)
    result = audit_experiment([r0, r1], manifest())
    assert result["identical_repeat_groups"] == [
        {"task_id": "t1", "condition": "native", "repetitions": 2}]
    report = render_markdown(result)
    assert "identical recorded decisions" in report
    assert "not proof" in report


def test_reject_mismatched_or_duplicate_runs():
    row = make_record()
    with pytest.raises(ValueError, match="Duplicate"):
        audit_experiment([row, row], manifest())
    wrong = make_record()
    wrong["experiment_id"] = "other"
    with pytest.raises(ValueError, match="does not belong"):
        audit_experiment([wrong], manifest())


def test_seeded_oracle_counts_even_without_tools():
    row = make_record("oracle")
    row["intervention"] = {"sources": [{"path": "fix.py"}]}
    row["trajectory"] = []
    result = audit_record(row, ["fix.py"])
    assert result["oracle_observed"]
    assert result["first_read_is_oracle"] is None


def test_audit_cli_writes_markdown_and_json_without_inference(tmp_path, monkeypatch):
    import json
    from scripts import audit_experiment as cli

    run_dir = tmp_path / "runs" / "audit-test"
    run_dir.mkdir(parents=True)
    (run_dir / "t1__native__r00.json").write_text(json.dumps(make_record()))
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "load_manifest", lambda _: manifest())
    assert cli.main(["--manifest", "example.json"]) == 0
    markdown = tmp_path / "reports" / "audit-test.audit.md"
    structured = tmp_path / "reports" / "audit-test.audit.json"
    assert markdown.exists() and structured.exists()
    assert "Off-target reads" in markdown.read_text()
    assert json.loads(structured.read_text())["total_runs"] == 1


def test_misleading_exposure_and_wrong_locus_patch_are_audited():
    row = make_record("misleading")
    row["intervention"] = {"sources": [{"path": "decoy.py"}]}
    row["proposal"] = {"path": "decoy.py"}
    audited = audit_record(row, ["fix.py"], ["decoy.py"])
    assert audited["seeded_misleading"] is True
    assert audited["patch_in_misleading_file"] is True
    assert audited["patch_in_oracle_file"] is False
