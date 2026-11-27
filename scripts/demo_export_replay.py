"""Show two outcomes of correcting a corrupt export using a local fixture."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from patchscope.evaluation_git import apply_to_index, git, temporary_patch_index
from scripts.replay_export import replay


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "export_replay"
FILE = "calculator.py"
SOURCE = (FIXTURES / FILE).read_text(encoding="utf-8")
CONTEXT_LINE, OLD_LINE = SOURCE.splitlines()
EXPECTED = 3.5


def prepare_fixture(repo):
    git(repo, "init", "--quiet")
    (repo / FILE).write_bytes(SOURCE.encode("utf-8"))
    git(repo, "add", "--", FILE)
    git(repo, "-c", "user.name=PatchScope Demo", "-c", "user.email=demo@example.invalid",
        "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={repo / '.git' / 'no-hooks'}",
        "commit", "--quiet", "-m", "Add average fixture")
    return git(repo, "rev-parse", "HEAD").decode().strip()


def saved_episode(base, replacement):
    # The historical renderer concatenated unterminated hunk lines.
    original = (
        f"--- a/{FILE}\n+++ b/{FILE}\n@@ -1,2 +1,2 @@\n"
        f" {CONTEXT_LINE}\n-{OLD_LINE}+{replacement}"
    )
    return {
        "task_id": "demo-average",
        "provenance": {"base_commit": base},
        "proposal": {
            "path": FILE,
            "start_line": 2,
            "end_line": 2,
            "expected_sha256": hashlib.sha256(OLD_LINE.encode("utf-8")).hexdigest(),
            "replacement": replacement,
        },
        "proposal_diff": original,
    }


def demo_case(repo, base, replacement):
    episode = saved_episode(base, replacement)
    corrected, report = replay(repo, episode, episode["proposal_diff"].encode("utf-8"))
    if ("corrupt patch" not in (report["original_git_rejection"] or "").lower()
            or not report["legacy_renderer_reproduces_original_bytes"]):
        raise ValueError("The fixture did not reproduce the corrupt legacy export")
    with temporary_patch_index(repo) as index:
        apply_to_index(index, base, corrected)
        source = git(index, "show", f":{FILE}")
    # Execute the demo's own calculator fixture from the applied Git index.
    namespace = {}
    exec(compile(source, FILE, "exec"), namespace)
    return namespace["average"](2, 5)


def main():
    cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="patchscope-export-demo-") as directory:
        repo = Path(directory)
        base = prepare_fixture(repo)
        for case in cases:
            label = case["label"]
            actual = demo_case(repo, base, case["replacement"])
            passed = actual == EXPECTED
            if passed != case["expected_pass"]:
                raise ValueError(f"Unexpected functional check result for {label}")
            print(f"{label}\n"
                  "  Original export: rejected by Git (corrupt patch)\n"
                  "  Corrected export: applied and matched the intended tree\n"
                  f"  average(2, 5): expected {EXPECTED}, got {actual} "
                  f"({'PASS' if passed else 'FAIL'})\n")
    print("Both cases verified with local fixture checks.")


if __name__ == "__main__":
    main()
