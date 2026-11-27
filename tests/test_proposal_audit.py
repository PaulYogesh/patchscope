from patchscope.proposal_audit import audit_proposals, render_proposal_audit


def test_archived_proposal_audit_does_not_export_response_text():
    rec = {
        "task_id": "x", "condition": "bm25", "repetition": 0,
        "outcome": {"status": "error"},
        "transcript": [{"role": "assistant", "purpose": "patch_proposal", "content": "NOT_JSON_PRIVATE_PAYLOAD"}],
        "usage": {"usage_events": [{"purpose": "patch_proposal", "completion_tokens": 450}]},
        "budgets": {"max_completion_tokens_per_call": 450},
    }
    result = audit_proposals([rec])
    md = render_proposal_audit(result)
    assert result["groups"][0]["original_response"]["code"] == "patch_json_invalid_or_missing"
    assert "450 / 450" in md
    assert "NOT_JSON_PRIVATE_PAYLOAD" not in md


def test_audit_cli_preserves_existing_main_report(tmp_path, monkeypatch):
    import json
    from scripts import audit_proposals as cli

    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "load_manifest", lambda _: {"experiment_id": "pilot-v02"})
    old = tmp_path / "reports" / "pilot-v02.md"
    old.parent.mkdir(parents=True)
    old.write_text("ORIGINAL REPORT — DO NOT OVERWRITE")
    logs = tmp_path / "runs" / "pilot-v02"
    logs.mkdir(parents=True)
    (logs / "sample.json").write_text(json.dumps({
        "task_id": "a", "condition": "native", "repetition": 0,
        "experiment_id": "pilot-v02", "outcome": {"status": "resolved"},
        "transcript": [], "usage": {}, "budgets": {},
    }))
    assert cli.main(["--manifest", "unused.json"]) == 0
    assert old.read_text() == "ORIGINAL REPORT — DO NOT OVERWRITE"
    assert (old.parent / "pilot-v02.proposals.md").exists()
    assert (old.parent / "pilot-v02.proposals.json").exists()
