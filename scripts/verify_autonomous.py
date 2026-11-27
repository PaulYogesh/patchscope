import hashlib
import json
from pathlib import Path

from patchscope.repair import (
    temporary_repo,
    apply_exact_edit,
    run_pytest,
)
from patchscope.tools import list_source_files


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "mini_repo"
PROPOSAL_FILE = ROOT / "runs" / "autonomous_proposal.json"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    record = json.loads(
        PROPOSAL_FILE.read_text(encoding="utf-8")
    )
    proposal = record["proposal"]

    if (
        not isinstance(proposal, dict)
        or set(proposal) != {"path", "old", "new"}
        or not all(isinstance(v, str)
                   for v in proposal.values())
    ):
        raise ValueError("Invalid proposal format")

    path = proposal["path"]

    if path not in record["inspected_files"]:
        raise ValueError("Target file was not inspected")

    if path not in list_source_files(FIXTURE):
        raise ValueError("Unapproved source file")

    source = FIXTURE / path
    original_hash = file_hash(source)

    if original_hash != record["source_sha256"]:
        raise ValueError("Source hash mismatch")

    with temporary_repo(FIXTURE) as repo:
        before = run_pytest(repo)

        edit = apply_exact_edit(
            repo,
            path,
            proposal["old"],
            proposal["new"],
        )

        after = run_pytest(repo)

    unchanged = file_hash(source) == original_hash

    verified = (
        not before["passed"]
        and edit["applied"]
        and after["passed"]
        and unchanged
    )

    repeated_reads = sum(
        event.get("repeated_read", False)
        for event in record["events"]
    )

    result = {
        "task_id": record["task_id"],
        "model": record["model"],
        "target_file": path,
        "files_inspected": record["inspected_files"],
        "tool_calls": len(record["events"]),
        "repeated_read_requests": repeated_reads,
        "prompt_tokens": record["prompt_tokens"],
        "completion_tokens": record["completion_tokens"],
        "buggy_tests_passed": before["passed"],
        "repaired_tests_passed": after["passed"],
        "original_unchanged": unchanged,
        "repair_verified": verified,
    }

    output = ROOT / "runs" / "autonomous_result.json"
    output.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))
    print("\nPytest result:")
    print(after["output"])

    if not verified:
        raise SystemExit("Autonomous repair verification failed")


if __name__ == "__main__":
    main()
