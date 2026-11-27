import pytest
from pathlib import Path

from patchscope.repair import (
    apply_exact_edit,
    run_pytest,
    temporary_repo,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "mini_repo"


def test_repair_passes_tests_and_preserves_original():
    original = (FIXTURE / "calculator.py").read_bytes()

    with temporary_repo(FIXTURE) as repo:
        before = run_pytest(repo)

        apply_exact_edit(
            repo,
            "calculator.py",
            "return sum(values) // len(values)",
            "return sum(values) / len(values)",
        )

        after = run_pytest(repo)

        assert before["passed"] is False
        assert after["passed"] is True

    assert (FIXTURE / "calculator.py").read_bytes() == original


def test_cannot_modify_tests():
    with temporary_repo(FIXTURE) as repo:
        with pytest.raises(ValueError):
            apply_exact_edit(
                repo,
                "test_calculator.py",
                "assert",
                "pass",
            )


def test_cannot_edit_outside_repository():
    with temporary_repo(FIXTURE) as repo:
        with pytest.raises(ValueError):
            apply_exact_edit(
                repo,
                "../README.md",
                "old",
                "new",
            )


def test_rejects_ambiguous_replacement():
    with temporary_repo(FIXTURE) as repo:
        with pytest.raises(ValueError):
            apply_exact_edit(
                repo,
                "calculator.py",
                "values",
                "numbers",
            )
