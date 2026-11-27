import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.demo_paired_repair import ISSUE, demo


class OfflineDemoTests(unittest.TestCase):
    def test_export_changes_only_average_and_keeps_source_checkout_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            console = io.StringIO()
            with contextlib.redirect_stdout(console):
                self.assertEqual(demo(root), 0)

            baseline = root / "baseline" / ISSUE
            candidate = root / "candidate" / ISSUE
            self.assertFalse((baseline / "prediction.jsonl").exists())
            prediction = json.loads((candidate / "prediction.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(prediction["instance_id"], ISSUE)
            self.assertIn("exported / ungraded", console.getvalue())

            original = candidate / "repo"
            status = subprocess.check_output(["git", "status", "--porcelain"], cwd=original)
            self.assertEqual(status, b"")
            scratch = Path(temporary) / "patch-verification"
            subprocess.run(
                ["git", "clone", "--quiet", "--local", str(original), str(scratch)], check=True,
            )
            subprocess.run(["git", "apply", "-"], cwd=scratch,
                           input=prediction["model_patch"], text=True, check=True)
            expected = (
                "def subtract(x, y):\n"
                "    return x - y\n\n"
                "def average(x, y):\n"
                "    return (x + y) / 2\n"
            )
            self.assertEqual((scratch / "calculator.py").read_text(encoding="utf-8"), expected)
