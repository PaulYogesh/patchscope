"""Offline regressions for opt-in SWE-bench navigation tools."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from patchscope.agent import _tool_result, run_episode
from patchscope.navigation import NavigationError, read_file_range, search_code
from patchscope.protocol import TOOL_MODE_NATIVE_REQUIRED, ToolProtocolError, decode_message
from patchscope.swebench_dev import external_manifest


def action(name, **kwargs):
    return NS(name=name, arguments=kwargs)


class FakeClient:
    def __init__(self, replies, tokens_per_call=110):
        self.replies = list(replies)
        self.calls = []
        self.tokens = tokens_per_call
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content, requests = self.replies.pop(0)
        calls = [NS(id=f"call-{len(self.calls)}-{i}", type="function",
                    function=NS(name=name, arguments=json.dumps(args)))
                 for i, (name, args) in enumerate(requests)]
        return NS(choices=[NS(message=NS(content=content, tool_calls=calls),
                              finish_reason="tool_calls" if calls else "stop")],
                  usage=NS(prompt_tokens=self.tokens-20, completion_tokens=20))


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "repo").mkdir()
        (self.root / "repo" / "app.py").write_text(
            "def value():\n" + "    x = 1\n" * 90 + "    return 2\n")
        (self.root / "repo" / "test_hidden.py").write_text("SECRET_EVALUATOR = 3\n")
        (self.root / "issue.md").write_text("value should return 3")

    def test_range_reaches_noninitial_lines(self):
        result = read_file_range(self.root / "repo", "app.py", 88, 93)
        self.assertIn("return 2", result["content"])
        self.assertEqual(result["start_line"], 88)
        self.assertEqual(result["total_lines"], 92)
        with self.assertRaises(NavigationError):
            read_file_range(self.root / "repo", "test_hidden.py", 1, 2)
        with self.assertRaises(NavigationError):
            read_file_range(self.root / "repo", "app.py", 1, 100)
        with self.assertRaises(NavigationError):
            read_file_range(self.root / "repo", "../issue.md", 1, 1)

    def test_search_is_bounded_and_excludes_tests(self):
        result = search_code(self.root / "repo", "return 2")
        self.assertEqual(result["hits"][0]["line"], 92)
        self.assertFalse(search_code(self.root / "repo", "SECRET_EVALUATOR")["hits"])
        with self.assertRaises(NavigationError):
            search_code(self.root / "repo", "x")

    def test_navigation_inventory_and_prefix_exclude_test_helpers(self):
        repo = self.root / "repo"
        (repo / "tests").mkdir()
        (repo / "tests" / "support.py").write_text("expected = 3\n")
        observed = {}
        inventory, _, valid = _tool_result(repo, action("list_files"), observed, exclude_tests=True)
        self.assertTrue(valid)
        self.assertEqual(inventory["files"], ["app.py"])
        _, _, valid = _tool_result(
            repo, action("read_file", path="tests/support.py"), observed, exclude_tests=True,
        )
        self.assertFalse(valid)
        self.assertEqual(observed, {})

    def test_repeated_range_is_detected(self):
        observed, seen = {}, set()
        a = action("read_file_range", path="app.py", start_line=88, end_line=92)
        first, repeated, valid = _tool_result(self.root / "repo", a, observed, seen)
        self.assertTrue(valid)
        self.assertFalse(repeated)
        self.assertIn("return 2", observed["app.py"])
        second, repeated, valid = _tool_result(self.root / "repo", a, observed, seen)
        self.assertTrue(repeated)
        self.assertTrue(second["already_provided"])
        self.assertEqual(observed["app.py"].count("return 2"), 1)

    def test_nav_tools_rejected_in_basic_episode(self):
        msg = NS(content=None, tool_calls=[NS(id="x", type="function", function=NS(
            name="search_code", arguments=json.dumps({"query":"value"})))])
        with self.assertRaises(ToolProtocolError):
            decode_message(msg, mode=TOOL_MODE_NATIVE_REQUIRED,
                           allowed_tools={"list_files", "read_file"})

    def test_original_agent_explores_range_and_proposes_patch(self):
        # A fake client asserts integration behavior; not an actual Qwen run.
        public = {"instance_id": "x__y-1", "repo": "x/y",
                  "base_commit": "a" * 40, "problem_statement": "value should return 3"}
        manifest, item = external_manifest(public, model="fake", max_steps=6)
        self.assertEqual(manifest["repo_tools_policy"], "navigation_v1")
        self.assertEqual(manifest["proposal_contract"], "line_range_hash_v1")
        self.assertEqual(manifest["budgets"]["proposal_reserve_tokens"], 4500)
        client = FakeClient([
            (None, [("search_code", {"query": "return 2"})]),
            (None, [("read_file_range", {"path": "app.py", "start_line": 88, "end_line": 92})]),
            ("Found issue.", []),
            (json.dumps({"path": "app.py", "start_line": 92, "end_line": 92,
                         "replacement": "    return 3\n"}), []),
        ])
        record = run_episode(item=item, manifest=manifest, root=self.root,
                             client=client, model="fake", provenance={})
        self.assertEqual(record["outcome"]["status"],
                         "proposal_requires_explicit_verification_opt_in")
        self.assertEqual(record["proposal"]["path"], "app.py")
        self.assertIn("search_code", [x["function"]["name"] for x in client.calls[0]["tools"]])
        self.assertEqual(record["usage"]["model_calls"], 4)
        self.assertFalse(record["outcome"]["repair_verified"])
        self.assertNotIn("return 3", (self.root / "repo" / "app.py").read_text())

    def test_exploration_reserves_budget_for_proposal(self):
        public = {"instance_id": "x__y-1", "repo": "x/y",
                  "base_commit": "a" * 40, "problem_statement": "value should return 3"}
        manifest, item = external_manifest(public, model="fake", max_steps=10)
        manifest["budgets"]["soft_total_token_budget"] = 900
        manifest["budgets"]["proposal_reserve_tokens"] = 400
        client = FakeClient([
            (None, [("read_file_range", {"path": "app.py", "start_line": 88, "end_line": 92})]),
            (None, [("search_code", {"query": "return 2"})]),
            (None, [("search_code", {"query": "value"})]),
            (None, [("search_code", {"query": "return 2"})]),
            (None, [("search_code", {"query": "value"})]),
            (json.dumps({"path": "app.py", "start_line": 92, "end_line": 92,
                         "replacement": "    return 3\n"}), []),
        ], tokens_per_call=110)
        record = run_episode(item=item, manifest=manifest, root=self.root,
                             client=client, model="fake", provenance={})
        self.assertTrue(record["proposal"])
        self.assertEqual(record["usage"]["model_calls"], 6)
        self.assertTrue(any(t["kind"] == "exploration_stopped_for_proposal_budget"
                            for t in record["trajectory"]))


if __name__ == "__main__":
    unittest.main()
