import hashlib
import json
import sys
import unittest

import test_swebench_dev as fixtures
from test_swebench_dev_agent import FakeClient
from patchscope.agent import run_episode
from patchscope.swebench_aider import run_aider_pilot
from patchscope.swebench_dev import DATASET, external_manifest, load_prepared, save_episode_prediction
from scripts.report_swebench_dev_pair import compare
from scripts.replay_swebench_windows import run_native_replay


class AiderComparatorTests(unittest.TestCase):
    setUp = fixtures.SWEbenchDevAdapterTests.setUp
    prepare = fixtures.SWEbenchDevAdapterTests.prepare

    def baseline_episode(self):
        workspace = self.prepare()
        public = load_prepared(workspace)
        record = {
            "task_id": public["instance_id"], "condition": "native",
            "provenance": {
                "benchmark": DATASET, "split": "dev", "base_commit": self.sha,
                "generation": {"model": "qwen3.5:9b", "seed": 62000},
                "public_issue_sha256": hashlib.sha256(public["problem_statement"].encode()).hexdigest(),
            },
            "observed_paths": ["calculator.py"],
            "budgets": {"max_steps": 10},
            "outcome": {"status": "incomplete", "repair_verified": False},
        }
        (workspace / "episode.json").write_text(json.dumps(record), encoding="utf-8")
        return workspace

    def editor(self, action):
        executable = self.root / "fake-aider"
        executable.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            "import sys\n"
            "assert '--no-auto-test' in sys.argv and '--no-suggest-shell-commands' in sys.argv\n"
            "assert sys.argv[-1] == './calculator.py'\n"
            "assert not Path('test_calculator.py').exists()\n"
            "message = Path(sys.argv[sys.argv.index('--message-file') + 1]).read_text()\n"
            "assert 'arithmetic mean' in message and 'GOLD_SECRET' not in message\n"
            + action + "\n",
            encoding="utf-8",
        )
        executable.chmod(0o700)
        return executable

    def test_scoped_edit_exports_against_original_checkout_and_pairs(self):
        baseline = self.baseline_episode()
        candidate = self.root / "aider"
        fixer = self.editor("Path('calculator.py').write_text('def average(x, y):\\n    return (x + y) / 2\\n')")
        record, prediction = run_aider_pilot(
            baseline, candidate, aider=fixer, ollama_url="http://127.0.0.1:11434")
        self.assertIsNotNone(prediction)
        self.assertTrue(record["static_review"]["passed"])
        self.assertIsNone(record["usage"]["total_tokens"])
        self.assertIn("+    return (x + y) / 2", json.loads(prediction.read_text())["model_patch"])
        for workspace in (baseline, prediction.parent):
            self.assertEqual((workspace / "repo" / "calculator.py").read_text(),
                             "def average(x, y):\n    return x - y\n")
        report_args = ([baseline.name], (baseline.parent, {}, None, None),
                       (candidate, {baseline.name: "resolved"}, None, None))
        paired = compare(*report_args, editor_comparison=True)
        self.assertEqual(paired["paired_resolution"], {"gain": 1})
        original = baseline / "episode.json"
        original.write_text(original.read_text() + "\n")
        mismatched = compare(*report_args, editor_comparison=True)
        self.assertEqual(mismatched["paired_resolution"], {"unavailable": 1})

    def test_matched_comparison_uses_full_files_and_requires_their_hash(self):
        target = self.original / "calculator.py"
        tail = "# filler\n" * 250 + "# shared evidence tail\n"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(tail)
        fixtures.git(["commit", "-qam", "Add evidence beyond read prefix"], self.original)
        self.record["base_commit"] = self.sha = fixtures.git(["rev-parse", "HEAD"], self.original)
        baseline = self.baseline_episode()
        saved = baseline / "episode.json"
        provenance = json.loads(saved.read_text())["provenance"]
        saved.unlink()
        manifest, item = external_manifest(load_prepared(baseline), model="qwen3.5:9b", matched_source=True)
        client = FakeClient()
        native = run_episode(item=item, manifest=manifest, root=baseline, client=client,
                             model="qwen3.5:9b", provenance=provenance)
        self.assertIn("shared evidence tail", client.requests[-1]["messages"][1]["content"])
        self.assertIsNotNone(save_episode_prediction(baseline, native, model="qwen3.5:9b"))

        candidate = self.root / "aider"
        fixer = self.editor(
            "p = Path('calculator.py')\n"
            "source = p.read_text()\n"
            "assert '# shared evidence tail' in source\n"
            "p.write_text(source.replace('return x - y', 'return (x + y) / 2'))"
        )
        aider, prediction = run_aider_pilot(
            baseline, candidate, aider=fixer, ollama_url="http://127.0.0.1:11434")
        self.assertIsNotNone(prediction)
        self.assertEqual(native["proposal_source"], aider["proposal_source"])
        report_args = ([baseline.name], (baseline.parent, {baseline.name: "unresolved"}, None, None),
                       (candidate, {baseline.name: "resolved"}, None, None))
        self.assertEqual(compare(*report_args, matched_source_comparison=True)["paired_resolution"], {"gain": 1})
        aider["proposal_source"]["sha256"] = "different"
        (prediction.parent / "episode.json").write_text(json.dumps(aider), encoding="utf-8")
        report = compare(*report_args, matched_source_comparison=True)
        self.assertIn("proposal_source", report["issues"][0]["metadata_differences"])
        self.assertEqual(report["paired_resolution"], {"unavailable": 1})

    def test_replayed_window_uses_original_coordinates_and_preserves_surrounding_source(self):
        target = self.original / "calculator.py"
        before = "# unseen header\n\ndef average(x, y):\n    return x - y\n# unseen tail\n"
        target.write_text(before, encoding="utf-8")
        fixtures.git(["commit", "-qam", "Add surrounding lines"], self.original)
        self.record["base_commit"] = self.sha = fixtures.git(["rev-parse", "HEAD"], self.original)
        source = self.baseline_episode()
        saved = source / "episode.json"
        origin = json.loads(saved.read_text())
        origin["trajectory"] = [
            {"kind": "tool_result", "name": "read_file_range", "result": {
                "path": "calculator.py", "start_line": 4,
                "content": "    return x - y\n# unseen"}},
        ]
        saved.write_text(json.dumps(origin), encoding="utf-8")
        raw = saved.read_bytes()
        client = FakeClient()
        proposed = json.loads(client.responses[-1][0])
        proposed.update(start_line=4, end_line=4)
        client.responses = [(json.dumps(proposed), [])]
        native_root = self.root / "native"
        native, prediction = run_native_replay(source, native_root, client=client)
        self.assertIsNotNone(prediction)
        self.assertEqual(native["usage"]["tool_calls"], 0)
        self.assertEqual(len(client.requests), 1)
        prompt = client.requests[0]["messages"][1]["content"]
        self.assertIn("4:     return x - y", prompt)
        self.assertNotIn("unseen", prompt)
        self.assertEqual(saved.read_bytes(), raw)

        candidate_root = self.root / "aider-replay"
        fixer = self.editor(
            "p = Path('calculator.py')\n"
            "assert p.read_text() == '    return x - y\\n'\n"
            "p.write_text('    return (x + y) / 2\\n')"
        )
        aider, export = run_aider_pilot(prediction.parent, candidate_root, aider=fixer,
                                      ollama_url="http://127.0.0.1:11434")
        self.assertIsNotNone(export)
        self.assertEqual(native["proposal_source"], aider["proposal_source"])
        native_patch = json.loads(prediction.read_text())["model_patch"]
        self.assertEqual(json.loads(export.read_text())["model_patch"], native_patch)
        with (export.parent / "aider.diff").open("w", encoding="utf-8") as handle:
            handle.write(native_patch)
        fixtures.git(["apply", str(export.parent / "aider.diff")], export.parent / "repo")
        self.assertEqual((export.parent / "repo" / "calculator.py").read_text(),
                         before.replace("return x - y", "return (x + y) / 2"))

    def test_rejects_new_files_and_invalid_python(self):
        baseline = self.baseline_episode()
        for name, action, status in (
            ("new", "Path('extra.py').write_text('pass\\n')", "editor_edit_out_of_scope"),
            ("syntax", "Path('calculator.py').write_text('def average(:\\n')", "python_syntax_invalid"),
        ):
            with self.subTest(name=name):
                record, prediction = run_aider_pilot(
                    baseline, self.root / name, aider=self.editor(action),
                    ollama_url="http://127.0.0.1:11434")
                self.assertIsNone(prediction)
                self.assertEqual(record["outcome"]["status"], status)
                self.assertFalse(record["outcome"]["repair_verified"])
