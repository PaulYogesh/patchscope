import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from patchscope.evaluation_git import git
from scripts.demo_export_replay import FILE, SOURCE, prepare_fixture, saved_episode


ROOT = Path(__file__).resolve().parents[1]


class ExportReplayTests(unittest.TestCase):
    def test_cli_accepts_a_relative_repo_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "calculator-repo"
            repo.mkdir()
            base = prepare_fixture(repo)
            episode = root / "episode.json"
            episode.write_text(
                json.dumps(saved_episode(base, "    return (x + y) / 2")), encoding="utf-8"
            )

            result = subprocess.run(
                [sys.executable, "-m", "scripts.replay_export", "--repo", repo.name,
                 "--episode", episode.name],
                cwd=root, env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["corrected_tree"], report["intended_tree"])

    def test_cli_recovers_corrupt_export_without_changing_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            base = prepare_fixture(repo)
            replacement = "    return (x + y) / 2"
            episode = root / "episode.json"
            episode.write_text(json.dumps(saved_episode(base, replacement)), encoding="utf-8")
            patch = root / "corrected.diff"

            result = subprocess.run(
                [sys.executable, "-m", "scripts.replay_export", "--repo", str(repo),
                 "--episode", str(episode), "--write-patch", str(patch)],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            report = json.loads(result.stdout)

            self.assertIn("corrupt patch", report["original_git_rejection"])
            self.assertTrue(report["legacy_renderer_reproduces_original_bytes"])
            self.assertIsNone(report["original_tree"])
            self.assertEqual(report["corrected_tree"], report["intended_tree"])
            self.assertEqual(report["new_model_calls"], 0)
            self.assertIsNone(report["archived_grade"])
            self.assertEqual((repo / FILE).read_bytes(), SOURCE.encode("utf-8"))
            self.assertEqual(git(repo, "status", "--porcelain"), b"")

            written = patch.read_bytes()
            self.assertEqual(written.count(b"\\ No newline at end of file\n"), 2)
            git(repo, "apply", str(patch))
            self.assertEqual((repo / FILE).read_bytes(),
                             f"def average(x, y):\n{replacement}".encode("utf-8"))

    def test_demo_distinguishes_export_recovery_from_functional_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.demo_export_replay"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.count("Original export: rejected by Git"), 2)
        self.assertEqual(result.stdout.count("Corrected export: applied"), 2)
        self.assertIn("average(2, 5): expected 3.5, got 3.5 (PASS)", result.stdout)
        self.assertIn("average(2, 5): expected 3.5, got 3 (FAIL)", result.stdout)


if __name__ == "__main__":
    unittest.main()
