import hashlib
import json
from pathlib import Path

from patchscope.repair import (
    temporary_repo,
    apply_exact_edit,
    run_pytest,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "mini_repo"
PROPOSAL_FILE = ROOT / "runs" / "day4_proposal.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    record = json.loads(
        PROPOSAL_FILE.read_text(encoding="utf-8")
    )

    proposal = record["proposal"]

    # Verify that the proposal belongs to the source
    # version that was shown to the model.
    source = FIXTURE / "calculator.py"
    original_hash = sha256(source)

    if original_hash != record["source_sha256"]:
        raise ValueError(
            "Source changed since proposal generation"
        )

    print("Model:", record["model"])
    print("Proposal:", json.dumps(proposal))
    print("Source hash verified:", True)

    with temporary_repo(FIXTURE) as repo:
        # Evaluate the buggy state.
        before = run_pytest(repo)

        # Apply the actual LLM-generated proposal.
        edit_result = apply_exact_edit(
            repo,
            proposal["path"],
            proposal["old"],
            proposal["new"],
        )

        # Evaluate the repaired state.
        after = run_pytest(repo)

        print("\n--- Verification ---")
        print("Buggy tests passed:", before["passed"])
        print("Edit applied:", edit_result["applied"])
        print("Repaired tests passed:", after["passed"])

        print("\n--- Pytest output ---")
        print(after["output"])

        verified = (
            not before["passed"]
            and edit_result["applied"]
            and after["passed"]
        )

    # Temporary repository has now been deleted.
    unchanged = sha256(source) == original_hash

    print("\n--- Final result ---")
    print("Model repair verified:", verified)
    print("Original source unchanged:", unchanged)

    result = {
        "task_id": "mini-average-001",
        "model": record["model"],
        "repair_verified": verified,
        "original_unchanged": unchanged,
        "prompt_tokens": record["prompt_tokens"],
        "completion_tokens": record["completion_tokens"],
    }

    output = ROOT / "runs" / "day4_result.json"
    output.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print("\nResult saved to:", output)

    if not verified or not unchanged:
        raise SystemExit("Verification failed")


if __name__ == "__main__":
    main()
