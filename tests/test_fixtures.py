
import pytest

from patchscope.experiment import load_manifest, PROJECT_ROOT
from patchscope.repair import apply_exact_edit, run_pytest, temporary_repo

FIXES = {
    "mini-average-001": ("calculator.py", "return sum(values) // len(values)", "return sum(values) / len(values)"),
    "mini-clamp-002": ("limits.py", "return max(upper, min(lower, value))", "return max(lower, min(upper, value))"),
    "mini-slug-003": ("text_ops.py", 'return text.lower().strip().replace(" ", "-")', 'return "-".join(text.lower().split())'),
    "mini-discount-004": ("checkout.py", "price * (1 + discount_percent / 100)", "price * (1 - discount_percent / 100)"),
}


@pytest.mark.parametrize("task", load_manifest(PROJECT_ROOT / "experiments" / "pilot_v02.json")["tasks"])
def test_bug_fixture_fails_before_and_passes_with_reference_fix(task):
    assert task["trusted_execution"]
    repo = PROJECT_ROOT / task["repo_path"]
    before_bytes = {p.name: p.read_bytes() for p in repo.glob("*.py")}
    with temporary_repo(repo) as work:
        baseline = run_pytest(work)
        path, old, new = FIXES[task["task_id"]]
        apply_exact_edit(work, path, old, new)
        corrected = run_pytest(work)
        assert baseline["passed"] is False, task["task_id"]
        assert corrected["passed"] is True, (task["task_id"], corrected)
    assert before_bytes == {p.name: p.read_bytes() for p in repo.glob("*.py")}


def test_misleading_decoys_do_not_fix_the_actual_bug():
    """Changing the misleading file alone must never fix the real defect."""
    manifest = load_manifest(PROJECT_ROOT / "experiments" / "interference_smoke_v030.json")
    expected = {
        "mini-average-001": ("return sum(values) // len(values)", "return sum(values) / len(values)"),
        "mini-clamp-002": ("return max(upper, min(lower, value))", "return max(lower, min(upper, value))"),
        "mini-slug-003": ('return text.lower().strip().replace(" ", "-")', 'return "-".join(text.lower().split())'),
        "mini-discount-004": ("price * (1 + discount_percent / 100)", "price * (1 - discount_percent / 100)"),
    }
    for task in manifest["tasks"]:
        repo = PROJECT_ROOT / task["repo_path"]
        decoy = task["misleading_pool"][0]
        assert decoy not in task["oracle"]["paths"]
        assert (repo / decoy).is_file()
        old, new = expected[task["task_id"]]
        with temporary_repo(repo) as work:
            assert run_pytest(work)["passed"] is False
            apply_exact_edit(work, decoy, old, new)
            assert run_pytest(work)["passed"] is False
