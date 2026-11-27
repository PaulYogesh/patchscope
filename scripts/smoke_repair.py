from pathlib import Path

from patchscope.repair import (
    temporary_repo,
    apply_exact_edit,
    run_pytest,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "mini_repo"

original_source = (
    FIXTURE / "calculator.py"
).read_text(encoding="utf-8")

with temporary_repo(FIXTURE) as working_repo:
    before = run_pytest(working_repo)

    print("Buggy tests passed:", before["passed"])

    # Known-correct edit used only to validate our executor.
    result = apply_exact_edit(
        working_repo,
        "calculator.py",
        "return sum(values) // len(values)",
        "return sum(values) / len(values)",
    )

    print("Edit result:", result)

    after = run_pytest(working_repo)

    print("Repaired tests passed:", after["passed"])

unchanged = (
    FIXTURE / "calculator.py"
).read_text(encoding="utf-8") == original_source

print("Original repository unchanged:", unchanged)

assert not before["passed"]
assert after["passed"]
assert unchanged
