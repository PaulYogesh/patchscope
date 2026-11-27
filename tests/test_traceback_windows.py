import unittest
from patchscope.traceback_windows import reposition, traceback_frames


class TracebackWindowTests(unittest.TestCase):
    def move(self, source, issue, width=4):
        old = {"path": "src/pkg/main.py", "start_line": 1,
               "content": "".join(source.splitlines(True)[:width])}
        new, reason = reposition(old, source, issue, traceback_frames(issue))
        self.assertLessEqual(len(new["content"].encode()), len(old["content"].encode()))
        self.assertLessEqual(len(new["content"].splitlines()), width)
        return old, new, reason

    def test_stale_frame_and_source_layout(self):
        source = "# enough bytes here\n" * 10 + "def f():\n    return 42\n"
        _, new, why = self.move(source, '  File "/opt/pkg/main.py", line 4, in f\n    return 42')
        self.assertIn("return 42", new["content"])
        self.assertIn("confirmed 12", why)

    def test_ambiguous_line_and_unrelated_paths(self):
        source = "# header\n" * 4 + "def f():\n    pass\n    pass\n"
        for path, line in [("pkg/main.py", 2), ("another/main.py", 6)]:
            old, new, _ = self.move(source, f'  File "{path}", line {line}, in f\n    pass')
            self.assertEqual(new, old)

    def test_named_method_precedes_deeper_frame(self):
        source = "# plenty of space per line\n" * 4 + "def api():\n    helper()\n" + "# spacer\n" * 10 + "def helper():\n    pass\n"
        issue = ('The api call fails.\nTraceback (most recent call last):\n'
                 '  File "pkg/main.py", line 6, in api\n    helper()\n'
                 '  File "pkg/main.py", line 18, in helper\n    pass')
        _, new, _ = self.move(source, issue)
        self.assertIn("    helper()", new["content"])

    def test_anchor_exceeds_budget(self):
        source = "#\n" * 4 + "def f():\n    return 'überlang'\n"
        old, new, why = self.move(source, '  File "pkg/main.py", line 6, in f\n    return \'überlang\'')
        self.assertEqual(old, new)
        self.assertIn("byte budget", why)

    def test_end_to_end_reference_scoring(self):
        import json
        from pathlib import Path
        import tempfile
        from patchscope.proposal_windows import describe_replayed_spans
        from patchscope.swebench_dev import DATASET, prepare_dev_instance
        from scripts.audit_swebench_windows import digest, git
        from scripts.probe_traceback_windows import freeze, report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "origin"
            repo.mkdir()
            git(repo, "init", "-q")
            (repo / "src/pkg").mkdir(parents=True)
            path = "src/pkg/main.py"
            header = "# room for proper context\n" * 4
            (repo / path).write_text(header + "# padding\n" * 19 + "def f():\n    return 42\n")
            git(repo, "add", ".")
            git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.org", "commit", "-qm", "base")
            base = git(repo, "rev-parse", "HEAD").decode().strip()
            issue = 'Error in f\n  File "/env/pkg/main.py", line 10, in f\n    return 42'
            row = {"instance_id": "pkg__pkg-1", "repo": "pkg/pkg", "base_commit": base,
                   "problem_statement": issue}
            folder = prepare_dev_instance(row, root / "baseline", clone_source=repo)
            windows = [{"path": path, "start_line": 1, "content": header}]
            episode = {"task_id": row["instance_id"], "proposal_windows": windows,
                       "proposal_source": describe_replayed_spans(windows), "provenance": {
                           "base_commit": base, "benchmark": DATASET, "split": "dev",
                           "public_issue_sha256": digest(issue.encode())}}
            (folder / "episode.json").write_text(json.dumps(episode))
            frozen = freeze(folder)
            (repo / path).write_text((repo / path).read_text().replace("return 42", "return 0"))
            row["patch"] = git(repo, "diff").decode()
            self.assertIn("| pkg__pkg-1 | 0/1 | 1/1 | 1 | 0 |", report([frozen], [row]))
            self.assertEqual(git(folder / "repo", "status", "--porcelain"), b"")
