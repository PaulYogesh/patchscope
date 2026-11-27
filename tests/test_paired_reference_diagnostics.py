"""Exercise the report CLI on archived grading artifacts and a pinned local repository."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from patchscope.swebench_dev import prepare_dev_instance
from scripts.audit_swebench_windows import git
from scripts.report_swebench_dev_pair import main, markdown


class PairedReferenceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.issue = "example__repo-1"
        repo = self.root / "src"
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / "x.py").write_text("x = 1\n")
        git(repo, "add", ".")
        git(repo, "-c", "user.name=T", "-c", "user.email=t@example.org", "commit", "-qm", "base")
        self.base = git(repo, "rev-parse", "HEAD").decode().strip()
        (repo / "x.py").write_text("x = 2\n")
        self.diff = git(repo, "diff").decode()
        git(repo, "restore", "x.py")
        task = dict(base_commit=self.base, repo="example/repo", instance_id=self.issue, problem_statement="wrong x")
        pred = dict(instance_id=self.issue, model_name_or_path="test", model_patch=self.diff)
        self.case = {"patch_successfully_applied": True, "resolved": False, "tests_status": {
            "FAIL_TO_PASS": {"success": ["target"], "failure": []},
            "PASS_TO_PASS": {"success": ["other"], "failure": ["existing"]}}}
        self.ids = self.root / "issues"
        self.ids.write_text(self.issue + "\n")
        self.args = ["--instances", str(self.ids), "--format", "json"]
        for arm in ("baseline", "candidate"):
            folder = prepare_dev_instance(task, self.root / arm, clone_source=repo)
            self.dump(folder / "episode.json", {"task_id": self.issue, "proposal": {"path": "x.py"},
                      "proposal_diff": self.diff, "condition": "native", "budgets": {"steps": 1},
                      "provenance": {"benchmark": "bench", "split": "dev", "base_commit": self.base,
                      "public_issue_sha256": "hash", "generation": {"model": "test"}}})
            self.dump(folder / "prediction.jsonl", pred)
            logs = self.root / "logs" / arm / "test"
            self.dump(logs / self.issue / "report.json", {self.issue: self.case})
            (logs / self.issue / "patch.diff").write_text(self.diff)
            summary = self.root / (arm + ".json")
            self.dump(summary, {"unresolved_ids": [self.issue], "submitted_ids": [self.issue]})
            self.args.extend(["--"+arm, str(folder.parent), "--"+arm+"-grader", str(summary),
                              "--"+arm+"-grader-root", str(logs)])
        self.ref = self.root / "reference.jsonl"
        self.dump(self.ref, dict(pred, model_name_or_path="ref"))
        self.grade = self.root / "logs" / "reference" / "ref" / self.issue / "report.json"
        self.dump(self.grade, {self.issue: self.case})
        (self.grade.parent / "patch.diff").write_text(self.diff + "\n")

    @staticmethod
    def dump(path, obj):
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(json.dumps(obj))

    def run_cli(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            main(self.args + list(args))
        return json.loads(output.getvalue())

    def test_reference_annotates_both_arms_without_regrading(self):
        old = self.run_cli()
        result = self.run_cli("--reference-control", self.base, str(self.ref), str(self.grade))
        text = markdown(result)
        notes = result.pop("unresolved_diagnostics")
        self.assertEqual(result, old)
        self.assertEqual(len(notes), 2)
        for note in notes:
            r = note["reference"]
            self.assertEqual(r["model_tree"], r["reference_tree"])
            self.assertTrue(r["both_grader_patches_verified"])
            self.assertEqual(note["target"]["success"], ["target"])
        self.assertIn("Official grade **unresolved**", text)
        self.assertIn("trees: **identical**", text)

    def test_no_control_and_missing_groups_remain_unknown(self):
        path = self.root / "logs/baseline/test" / self.issue / "report.json"
        self.dump(path, {self.issue: {"patch_successfully_applied": False, "resolved": False}})
        note = self.run_cli("--diagnose-unresolved")["unresolved_diagnostics"][0]
        self.assertIsNone(note["target"])
        self.assertIsNone(note["reference"])

    def test_mismatched_evidence_rejected_and_missing_link_disclosed(self):
        patch = self.grade.parent / "patch.diff"
        patch.unlink()
        args = ["--reference-control", self.base, str(self.ref), str(self.grade)]
        self.assertIn("unavailable for comparison", markdown(self.run_cli(*args)))
        patch.write_text("stale run")
        with self.assertRaises(SystemExit):
            self.run_cli(*args)
