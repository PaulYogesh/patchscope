"""Offline failure-triage regression tests."""

import copy
import pytest

from patchscope.failure_triage import error_category, failure_stage, render_triage, triage_records


MANIFEST = {"experiment_id": "triage-test", "conditions": ["native", "bm25", "placebo", "oracle"],
            "repetitions": 3, "tasks": [{"task_id": "t1"}, {"task_id": "t2"}]}


def record(task="t1", condition="native", rep=0, *, status="resolved", error=None, code="a"):
    return {
        "schema_version": 2, "experiment_id": "triage-test", "run_id": f"{task}__{condition}__r{rep:02d}",
        "task_id": task, "condition": condition, "repetition": rep,
        "outcome": {"status": status, "repair_verified": status == "resolved"},
        "error": error, "usage": {"total_tokens": 210, "usage_events": [{"purpose": "exploration"},
                     {"purpose": "patch_proposal"}]},
        "trajectory": [{"kind": "tool_call", "name": "list_files", "arguments": {}, "valid": True},
                       {"kind": "patch_proposal", "path": code, "old": "x", "new": "y"}]
                       if status == "resolved" else [{"kind": "tool_call", "name": "list_files", "arguments": {}, "valid": True}],
        "proposal": {"path": code, "old": "x", "new": "y"} if status == "resolved" else None,
        "intervention": {"seed_chars": 100 if condition in ("bm25", "oracle") else 0,
                         "sources": [{"path": "target.py"}] if condition in ("bm25", "oracle") else []},
    }


def test_failure_categories_expose_error_instead_of_assuming_bad_patch():
    r = record(status="error", error="ValueError: patch_old_fragment_not_unique_in_observed_code")
    assert error_category(r) == "patch_contract_validation"
    assert failure_stage(r) == "proposal_parsing_or_validation"
    r["error"] = "ValueError: model_call_budget_exhausted"
    assert error_category(r) == "resource_or_step_budget"
    r["error"] = "JSONDecodeError: Expecting value"
    assert error_category(r) == "patch_json_parsing"
    r["outcome"]["status"] = "repair_failed_tests"
    r["error"] = None
    assert failure_stage(r) == "patched_tests_failed"


def test_triage_detects_identical_repetition_and_seed_overlap():
    rows = []
    for rep in range(3):
        for condition in MANIFEST["conditions"]:
            status = "error" if condition in ("bm25", "oracle") else "resolved"
            err = "ValueError: invalid_patch_proposal" if status == "error" else None
            rows.append(record(condition=condition, rep=rep, status=status, error=err))
    result = triage_records(rows, MANIFEST)
    assert result["total_runs"] == 12
    assert result["identical_repeat_groups"] == 4
    assert result["distinct_task_condition_trajectories"] == 4
    assert len(result["failure_representatives"]) == 2
    assert all(r["repetitions_with_same_diagnosis"] == 3 for r in result["failure_representatives"])
    assert all(row["same_seeded_paths"] and row["same_trajectory"] for row in result["bm25_oracle_pairs"])
    markdown = render_triage(result, manifest=MANIFEST)
    assert "3/3" in markdown
    assert "observationally overlapping interventions" in markdown
    assert "patch_contract_validation" in markdown


def test_different_patches_count_as_distinct_trajectories():
    rows = [record(rep=0, code="a.py"), record(rep=1, code="b.py")]
    result = triage_records(rows, MANIFEST)
    assert result["distinct_task_condition_trajectories"] == 2
    assert result["identical_repeat_groups"] == 0


def test_triage_rejects_duplicates_and_foreign_experiment():
    r = record()
    with pytest.raises(ValueError, match="Duplicate"):
        triage_records([r, copy.deepcopy(r)], MANIFEST)
    foreign = copy.deepcopy(r)
    foreign["experiment_id"] = "other"
    with pytest.raises(ValueError, match="different experiment"):
        triage_records([foreign], MANIFEST)


def test_only_compact_error_text_is_reported():
    r = record(status="error", error="ValueError: " + "sensitive" * 300)
    result = triage_records([r], MANIFEST)
    assert len(result["failure_representatives"][0]["error"]) <= 171
    assert "\n" not in result["failure_representatives"][0]["error"]
