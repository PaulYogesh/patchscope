import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from patchscope.swebench_dev import FULL_DEV_DATASET
from scripts.trial_traceback_repair import select_tasks, validate
from scripts.replay_swebench_windows import run_native_replay
from test_swebench_dev_agent import FakeClient
import test_swebench_dev as fixtures


class TracebackTrialTests(unittest.TestCase):
    def test_selection_excludes_used_and_non_traceback_tasks_before_ranking(self):
        frame = '  File "app/main.py", line 4, in f\n    return x\n'
        rows = [{"instance_id": f"org__repo-{n}", "repo": "org/repo",
                 "problem_statement": frame if n else "no traceback", "base_commit": "a"*40,
                 "patch": "evaluator only"} for n in range(6)]
        chosen = select_tasks(rows, {"org__repo-2"})
        self.assertEqual(chosen, select_tasks(reversed(rows), {"org__repo-2"}))
        self.assertEqual({r["instance_id"] for r in chosen}, {"org__repo-1", "org__repo-3",
                                                              "org__repo-4", "org__repo-5"})
        self.assertTrue(all("patch" not in r for r in chosen))

    def test_paired_call_changes_actual_source_and_detects_wrong_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            from patchscope.swebench_dev import prepare_dev_instance
            root = Path(tmp)
            repo = root / "original"
            repo.mkdir()
            fixtures.git(["init", "-q"], repo)
            fixtures.git(["config", "user.name", "Example"], repo)
            fixtures.git(["config", "user.email", "example@example.org"], repo)
            header = "# long enough for a full statement\n"
            (repo / "calculator.py").write_text(header*30 + "def avg():\n    return 7\n")
            fixtures.git(["add", "."], repo)
            fixtures.git(["commit", "-qm", "base"], repo)
            task = {"repo": "org/repo", "instance_id": "org__repo-1",
                    "base_commit": fixtures.git(["rev-parse", "HEAD"], repo),
                    "problem_statement": 'Failure\n  File "calculator.py", line 4, in avg\n    return 7'}
            source = prepare_dev_instance(task, root / "exploration", clone_source=repo)
            episode = {"task_id": task["instance_id"], "condition": "native",
                       "observed_paths": ["calculator.py"], "trajectory": [{"kind": "tool_result",
                       "name": "read_file", "result": {"path": "calculator.py", "content": header*4}}],
                       "provenance": {"benchmark": FULL_DEV_DATASET, "split": "dev",
                       "base_commit": task["base_commit"], "generation": {"model": "qwen3.5:9b", "seed": 31},
                       "public_issue_sha256": hashlib.sha256(task["problem_statement"].encode()).hexdigest()}}
            (source / "episode.json").write_text(json.dumps(episode))
            for arm in ["baseline", "candidate"]:
                client = FakeClient()
                run_native_replay(source, root / arm, client=client, benchmark=FULL_DEV_DATASET,
                                  traceback_policy=arm == "candidate")
                prompt = client.requests[0]["messages"][1]["content"].split("Observed source:")[-1]
                self.assertEqual("return 7" in prompt, arm == "candidate")
            self.assertIn("| org__repo-1 | True", validate(root, [task]))
            with (source / "episode.json").open("a") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError, "provenance"):
                validate(root, [task])
