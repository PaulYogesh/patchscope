"""Evaluator-only diagnostics exercised against a real temporary Git base."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from patchscope.proposal_windows import describe_replayed_spans
from patchscope.swebench_dev import DATASET, prepare_dev_instance
from scripts.audit_swebench_windows import coverage, git, line_sets, locations, run


class WindowAuditTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.repo = self.root / "origin"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.file = self.repo / "sample.py"
        self.file.write_text("one\ntwo\nthree\nfour\nfive\nsix\n")
        git(self.repo, "add", ".")
        git(self.repo, "-c", "user.name=Test", "-c", "user.email=test@example.org",
            "commit", "-qm", "base")
        self.base = git(self.repo, "rev-parse", "HEAD").decode().strip()
        self.file.write_text("one\nchanged\nthree\nfour\nfive\nsix\nextra\n")
        self.patch = git(self.repo, "diff").decode()
        git(self.repo, "restore", "sample.py")

    def test_diff_context_and_insertion_edges(self):
        sites = locations(self.repo, self.base, self.patch)
        self.assertEqual(sites, [("sample.py", "text", 2, 1), ("sample.py", "text", 6, 0)])
        self.assertEqual(coverage(sites[0], {"sample.py": {1, 3}}), "outside range")
        self.assertEqual(coverage(sites[1], {"sample.py": {6}}), "covered")
        self.assertEqual(coverage(("sample.py", "text", 0, 0), {"sample.py": {1}}), "covered")
        self.assertEqual(coverage(("sample.py", "text", 4, 2), {"sample.py": {5}}), "partial")
        self.assertEqual(coverage(sites[0], {}), "path absent")
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_added_file(self):
        diff = "diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x\n"
        self.assertEqual(locations(self.repo, self.base, diff), [("new.py", "new file", 0, 0)])

    def test_partial_final_read_and_corrupt_span(self):
        read = [{"path": "sample.py", "start_line": 2, "content": "two\nthr"}]
        self.assertEqual(line_sets(read, self.repo, self.base, allow_partial=True), {"sample.py": {2}})
        with self.assertRaisesRegex(ValueError, "differs"):
            line_sets(read, self.repo, self.base, allow_partial=False)
        read[0]["content"] = "wrong"
        with self.assertRaisesRegex(ValueError, "differs"):
            line_sets(read, self.repo, self.base, allow_partial=True)

    def test_report_and_provenance(self):
        issue = "org__repo-1"
        public = {"instance_id": issue, "repo": "org/repo", "base_commit": self.base,
                  "problem_statement": "Handle the extra case"}
        replay = self.root / "replay"
        left = prepare_dev_instance(public, replay / "baseline", clone_source=self.repo)
        right = replay / "candidate" / issue
        right.mkdir(parents=True)
        archive = self.root / "exploration"
        old = archive / "baseline" / issue
        old.mkdir(parents=True)
        span = {"path": "sample.py", "start_line": 2, "content": "two\n"}
        sha = lambda b: hashlib.sha256(b).hexdigest()
        trace = json.dumps({"trajectory": [{"kind": "tool_result", "name": "read_file",
                            "result": {"path": "sample.py", "content": self.file.read_text()}}]}).encode()
        (old / "episode.json").write_bytes(trace)
        model = "test"
        episode = {"task_id": issue, "proposal_windows": [span],
                   "proposal_source": describe_replayed_spans([span]),
                   "provenance": {"base_commit": self.base, "split": "dev", "benchmark": DATASET,
                                  "generation": {"model": model}, "exploration_episode_sha256": sha(trace),
                                  "public_issue_sha256": sha(public["problem_statement"].encode())},
                   "outcome": {"status": "error"}}
        raw = json.dumps(episode).encode()
        (left / "episode.json").write_bytes(raw)
        episode.update(editor_comparator={"baseline_episode_sha256": sha(raw)}, proposal_diff=self.patch)
        (right / "episode.json").write_text(json.dumps(episode))
        (right / "prediction.jsonl").write_text(json.dumps({"model_patch": self.patch,
            "instance_id": issue, "model_name_or_path": model}))
        grades = self.root / "grades"
        (grades / issue).mkdir(parents=True)
        grade = {"resolved": False, "patch_successfully_applied": True,
                 "tests_status": {"FAIL_TO_PASS": {"success": [], "failure": ["unit::case"]}}}
        (grades / issue / "report.json").write_text(json.dumps({issue: grade}))
        args = (replay, archive, {"candidate": grades}, [{**public, "patch": self.patch}])
        text = run(*args)
        self.assertIn("| org__repo-1 | 2/2 | 1/2 | partial |", text)
        self.assertIn("FAIL_TO_PASS failure: `unit::case`", text)
        self.assertIn("Submitted edit", text)
        (old / "episode.json").write_bytes(trace + b"\n")
        with self.assertRaisesRegex(ValueError, "exploration episode hash mismatch"):
            run(*args)
