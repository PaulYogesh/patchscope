
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "mini_repo"


def run_tests(repo_path):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    return {
        "passed": result.returncode == 0,
        "exit_code": result.returncode,
        "output": result.stdout[-1000:],
    }


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = Path(temp_dir) / "repo"
        shutil.copytree(FIXTURE, repo)

        # Evaluate the original buggy state.
        before = run_tests(repo)

        # Apply a known-correct repair to a disposable copy.
        source = repo / "calculator.py"
        original = source.read_text()

        buggy_line = "return sum(values) // len(values)"
        fixed_line = "return sum(values) / len(values)"

        assert buggy_line in original

        source.write_text(
            original.replace(buggy_line, fixed_line)
        )

        # Evaluate the repaired state.
        after = run_tests(repo)

        result = {
            "task_id": "mini-average-001",
            "buggy_state_passed": before["passed"],
            "oracle_repair_passed": after["passed"],
            "validation_success": (
                not before["passed"] and after["passed"]
            ),
        }

        print(json.dumps(result, indent=2))

        assert result["validation_success"]


if __name__ == "__main__":
    main()
