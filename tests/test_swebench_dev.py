"""Offline, non-executing tests for the SWE-bench development adapter."""
from __future__ import annotations

import difflib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from patchscope.swebench_dev import (
    BenchmarkAdapterError, external_manifest, load_prepared, prepare_dev_instance,
    public_task, validate_and_export_prediction,
)


def git(args, cwd):
    cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if cp.returncode:
        raise AssertionError(cp.stderr)
    return cp.stdout.strip()


class SWEbenchDevAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / "source"
        self.original.mkdir()
        git(["init", "-q"], self.original)
        git(["config", "user.email", "test@example.invalid"], self.original)
        git(["config", "user.name", "Test"], self.original)
        (self.original / "calculator.py").write_text("def average(x, y):\n    return x - y\n", encoding="utf-8")
        (self.original / "test_calculator.py").write_text("# A test file must not be used as the gold patch\n")
        git(["add", "."], self.original)
        git(["commit", "-qm", "Initial broken state"], self.original)
        self.sha = git(["rev-parse", "HEAD"], self.original)
        self.record = {
            "instance_id": "example__repo-17", "repo": "example/repo",
            "base_commit": self.sha,
            "problem_statement": "Average should compute the arithmetic mean.",
            "patch": "GOLD_SECRET_DO_NOT_EXPOSE",
            "test_patch": "EVALUATOR_ONLY",
            "FAIL_TO_PASS": '["hidden::test"]',
            "PASS_TO_PASS": '["hidden::existing"]',
            "hints_text": "hindsight leaked!",
        }
        self.workspaces = self.root / "workspaces"

    def prepare(self):
        return prepare_dev_instance(self.record, self.workspaces, clone_source=self.original)

    def test_public_allowlist_excludes_all_evaluator_fields(self):
        result = public_task(self.record)
        self.assertEqual(set(result), {"instance_id", "repo", "base_commit", "problem_statement"})
        self.assertNotIn("GOLD_SECRET", json.dumps(result))

    def test_prepare_exact_checkout_and_no_hidden_files(self):
        folder = self.prepare()
        self.assertEqual(load_prepared(folder)["base_commit"], self.sha)
        self.assertEqual(git(["rev-parse", "HEAD"], folder / "repo"), self.sha)
        contents = (folder / "public_task.json").read_text() + (folder / "issue.md").read_text()
        self.assertNotIn("GOLD_SECRET", contents)
        self.assertNotIn("EVALUATOR_ONLY", contents)
        self.assertNotIn("hidden::", contents)
        self.assertNotIn("hindsight", contents)
        self.assertFalse((folder / "repo" / "issue.md").exists())

    def test_never_overwrites_a_prepared_workspace(self):
        self.prepare()
        with self.assertRaisesRegex(BenchmarkAdapterError, "already exists"):
            self.prepare()

    def test_detect_modified_repo_or_issue(self):
        folder = self.prepare()
        (folder / "issue.md").write_text("malicious replacement")
        with self.assertRaisesRegex(BenchmarkAdapterError, "Issue file changed"):
            load_prepared(folder)
        (folder / "issue.md").write_text(self.record["problem_statement"])
        (folder / "repo" / "calculator.py").write_text("modified")
        with self.assertRaisesRegex(BenchmarkAdapterError, "Tracked repository files changed"):
            load_prepared(folder)

    def test_detect_untracked_python_even_when_ignored(self):
        folder = self.prepare()
        repo = folder / "repo"
        (repo / ".git" / "info" / "exclude").write_text("extra.py\n")
        (repo / "extra.py").write_text("answer = 42\n")
        with self.assertRaisesRegex(BenchmarkAdapterError, "Untracked Python files"):
            load_prepared(folder)

    def test_manifest_reuses_native_agent_without_oracle_or_execution(self):
        manifest, item = external_manifest(public_task(self.record), model="qwen3.5:9b")
        self.assertEqual(manifest["conditions"], ["native"])
        self.assertFalse(item["task"]["trusted_execution"])
        self.assertEqual(item["task"]["oracle"]["paths"], [])
        self.assertEqual(item["task"]["placebo_pool"], [])
        self.assertNotIn("GOLD_SECRET", json.dumps(manifest))
        self.assertEqual(item["task"]["issue_path"], "issue.md")

    def test_prediction_export_is_git_applicable_and_schema_correct(self):
        folder = self.prepare()
        before = (folder / "repo" / "calculator.py").read_text()
        after = before.replace("x - y", "(x + y) / 2")
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile="a/calculator.py", tofile="b/calculator.py",
        ))
        episode = {"proposal": {"path": "calculator.py", "old": "x - y", "new": "(x + y) / 2"},
                   "proposal_diff": diff}
        dest = validate_and_export_prediction(folder, episode, model="qwen3.5:9b")
        output = json.loads(dest.read_text())
        self.assertEqual(set(output), {"instance_id", "model_name_or_path", "model_patch"})
        self.assertEqual(output["instance_id"], "example__repo-17")
        self.assertEqual(output["model_patch"], diff)
        self.assertEqual(git(["rev-parse", "HEAD"], folder / "repo"), self.sha)
        self.assertEqual((folder / "repo" / "calculator.py").read_text(), before)
        with self.assertRaisesRegex(BenchmarkAdapterError, "already exists"):
            validate_and_export_prediction(folder, episode, model="qwen3.5:9b")

    def test_bad_patches_are_not_exported(self):
        folder = self.prepare()
        with self.assertRaisesRegex(BenchmarkAdapterError, "does not apply"):
            validate_and_export_prediction(folder, {
                "proposal": {"path": "calculator.py"},
                "proposal_diff": "--- a/calculator.py\n+++ b/calculator.py\n@@ -1 +1 @@\n-no such line\n+new line\n",
            }, model="x")
        self.assertFalse((folder / "prediction.jsonl").exists())

    def test_export_checks_actual_path_against_declared_source(self):
        folder = self.prepare()
        path = "test_calculator.py"
        original = (folder / "repo" / path).read_text()
        diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True), ["# updated test\n"],
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
        with self.assertRaisesRegex(BenchmarkAdapterError, "exactly the declared Python source"):
            validate_and_export_prediction(folder, {
                "proposal": {"path": "calculator.py"}, "proposal_diff": diff,
            }, model="example")
        self.assertFalse((folder / "prediction.jsonl").exists())

    def test_reject_invalid_identifiers(self):
        for key, value in [
            ("repo", "../../outside"), ("repo", "owner/-bad"),
            ("instance_id", "../escape"), ("base_commit", "latest"),
        ]:
            with self.subTest(key=key, value=value):
                row = dict(self.record, **{key: value})
                with self.assertRaises(BenchmarkAdapterError):
                    public_task(row)


if __name__ == "__main__":
    unittest.main()
