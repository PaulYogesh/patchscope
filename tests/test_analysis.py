import pytest

from patchscope.analysis import exact_mcnemar, summarize, paired_task_bootstrap
from scripts.report_experiment import build_report


def record(task, condition, rep, repaired):
    return {"task_id": task, "condition": condition, "repetition": rep,
            "schema_version": 2, "experiment_id": "test",
            "outcome": {"repair_verified": repaired, "status": "resolved" if repaired else "error"},
            "usage": {"total_tokens": 100 if condition == "bm25" else 200,
                      "tool_calls": 1, "repeated_reads": 0, "retrieval_ms": 0,
                      "wall_seconds": 1}}


def test_exact_mcnemar_two_sided():
    assert exact_mcnemar(0, 0) == 1
    assert exact_mcnemar(5, 0) == .0625
    assert exact_mcnemar(2, 2) == 1


def test_bootstrap_requires_more_than_one_independent_task():
    result = paired_task_bootstrap([1])
    assert result["estimate"] == 1 and result["ci_low"] is None


def test_analysis_pairs_only_matching_task_and_repetition():
    rows = [record("task1", "bm25", 0, True), record("task1", "native", 0, False),
            record("task1", "bm25", 1, True), record("task2", "native", 0, True)]
    result = summarize(rows)
    paired = result["paired_contrasts"]["bm25 - native"]
    assert paired["matched_pairs"] == 1
    assert paired["a_only"] == 1 and paired["b_only"] == 0
    assert paired["repair_risk_difference"] == 1
    assert paired["bootstrap_95_low"] is None


def test_duplicate_runs_rejected():
    r = record("task1", "native", 0, True)
    with pytest.raises(ValueError, match="Duplicate"):
        summarize([r, r])


def test_report_is_neutral_and_reproducible():
    rows = [record("task1", "bm25", 0, True), record("task1", "native", 0, False)]
    report = build_report(rows, "test")
    assert "Task-cluster 95% CI" in report
    assert "mermaid" in report
    assert "not" in report.lower()


def test_opted_out_verification_is_not_counted_as_failure():
    from patchscope.analysis import summarize
    pending = record("task1", "bm25", 0, False)
    pending["outcome"]["status"] = "proposal_requires_explicit_verification_opt_in"
    native = record("task1", "native", 0, True)
    result = summarize([pending, native])
    assert result["conditions"]["bm25"]["repair_rate"] is None
    assert result["conditions"]["bm25"]["evaluated"] == 0
    assert result["paired_contrasts"]["bm25 - native"]["matched_pairs"] == 0


def test_repeated_task_pairs_do_not_produce_pseudoreplicated_mcnemar_p():
    rows = []
    for rep in range(3):
        rows.extend([record("clamp", "native", rep, True),
                     record("clamp", "bm25", rep, False)])
    paired = summarize(rows)["paired_contrasts"]["bm25 - native"]
    assert paired["matched_pairs"] == 3
    assert paired["b_only"] == 3
    assert paired["exact_mcnemar_p"] is None
    assert paired["mcnemar_suppressed_due_to_repeated_tasks"] is True
    assert "omitted" in build_report(rows, "test")
