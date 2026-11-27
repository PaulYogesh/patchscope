"""Offline integration: actual PatchScope run_episode is reused, no benchmark code runs."""
import hashlib
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import test_swebench_dev as _test_helpers
from patchscope.repair import apply_line_edit, temporary_repo
from patchscope.swebench_dev import external_manifest, public_task, validate_and_export_prediction

try:
    from patchscope.agent import run_episode
except ImportError:
    run_episode = None


class FakeClient:
    def __init__(self):
        self.responses = [
            (None, [("read_file", {"path": "calculator.py"})]),
            ("Evidence inspected.", []),
            (json.dumps({"path": "calculator.py", "start_line": 2, "end_line": 2,
                         "replacement": "    return (x + y) / 2\n"}), []),
        ]
        self.requests = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content, tool_calls = self.responses.pop(0)
        calls = [NS(id=f"call-{len(self.requests)}", type="function",
                    function=NS(name=name, arguments=json.dumps(args)))
                 for name, args in tool_calls]
        return NS(choices=[NS(message=NS(content=content, tool_calls=calls), finish_reason="stop")],
                  usage=NS(prompt_tokens=100, completion_tokens=20))


@unittest.skipIf(run_episode is None, "Core agent dependencies not available in this environment")
class ExternalPilotReuseTests(unittest.TestCase):
    setUp = _test_helpers.SWEbenchDevAdapterTests.setUp
    prepare = _test_helpers.SWEbenchDevAdapterTests.prepare

    def test_real_core_agent_on_prepared_historical_shape(self):
        workspace = self.prepare()
        public = public_task(self.record)
        manifest, item = external_manifest(public, model="fake")
        client = FakeClient()
        before = (workspace / "repo" / "calculator.py").read_bytes()
        with patch("patchscope.agent.run_pytest", side_effect=AssertionError("Host tests must never execute")):
            record = run_episode(item=item, manifest=manifest, root=workspace,
                                 client=client, model="fake", provenance={},
                                 allow_trusted_execution=False)
        self.assertEqual(record["outcome"]["status"], "proposal_requires_explicit_verification_opt_in")
        self.assertFalse(record["outcome"]["repair_verified"])
        self.assertEqual(record["proposal"]["path"], "calculator.py")
        self.assertEqual(record["usage"]["model_calls"], 3)
        self.assertEqual(record["usage"]["tool_calls"], 1)
        self.assertTrue(all("extra_body" not in request for request in client.requests))
        self.assertNotIn("proposal_reasoning_effort", record["provenance"]["generation"])
        self.assertEqual(before, (workspace / "repo" / "calculator.py").read_bytes())
        all_model_inputs = json.dumps(client.requests)
        for forbidden in ("GOLD_SECRET_DO_NOT_EXPOSE", "EVALUATOR_ONLY", "hidden::", "hindsight leaked!"):
            self.assertNotIn(forbidden, all_model_inputs)
        dest = validate_and_export_prediction(workspace, record, model="fake")
        self.assertEqual(json.loads(dest.read_text())["instance_id"], public["instance_id"])

    def test_reasoning_off_applies_only_to_proposals_and_retry(self):
        workspace = self.prepare()
        public = public_task(self.record)
        manifest, item = external_manifest(public, model="fake", proposal_reasoning_effort="none")
        client = FakeClient()
        client.responses.insert(2, ("", []))
        record = run_episode(item=item, manifest=manifest, root=workspace,
                             client=client, model="fake", provenance={})

        self.assertEqual(record["experiment_id"], "swebench_lite_dev_v09_proposal_reasoning_none")
        self.assertEqual(record["provenance"]["generation"]["proposal_reasoning_effort"], "none")
        self.assertEqual([request.get("extra_body") for request in client.requests],
                         [None, None, {"reasoning_effort": "none"}, {"reasoning_effort": "none"}])
        self.assertEqual([request["max_tokens"] for request in client.requests], [450, 450, 1600, 1600])
        self.assertEqual([attempt["valid"] for attempt in record["proposal_attempts"]], [False, True])
        self.assertEqual(record["usage"]["usage_events"][2]["visible_response_chars"], 0)
        self.assertFalse(record["usage"]["usage_events"][2]["reasoning_output_present"])
        self.assertIsNotNone(validate_and_export_prediction(workspace, record, model="fake"))

    def test_midfile_replacement_cannot_join_unedited_source_line(self):
        workspace = self.prepare()
        repo = workspace / "repo"
        target = repo / "calculator.py"
        target.write_text("def average(x, y):\n    return x - y\n"
                          "sentinel = 1\n", encoding="utf-8")
        before = target.read_bytes()
        manifest, item = external_manifest(public_task(self.record), model="fake")
        client = FakeClient()
        bad = {"path": "calculator.py", "start_line": 2, "end_line": 2,
               "replacement": "    return (x + y) / 2"}
        client.responses.insert(2, (json.dumps(bad), []))
        record = run_episode(item=item, manifest=manifest, root=workspace,
                             client=client, model="fake", provenance={})
        self.assertEqual([attempt["reason"] for attempt in record["proposal_attempts"]],
                         ["patch_replacement_missing_final_newline", None])
        self.assertIn("End a nonempty replacement", client.requests[3]["messages"][-1]["content"])
        self.assertIn("+    return (x + y) / 2\n", record["proposal_diff"])
        bad["expected_sha256"] = hashlib.sha256(b"    return x - y\n").hexdigest()
        with self.assertRaisesRegex(ValueError, "patch_replacement_missing_final_newline"):
            apply_line_edit(repo, bad)
        self.assertEqual(target.read_bytes(), before)

    def test_syntax_feedback_reuses_the_proposal_retry_budget(self):
        workspace = self.prepare()
        target = workspace / "repo" / "calculator.py"
        target.write_text("def average(x, y):\n    return (x + y) // 2\n"
                          "sentinel = 1\n", encoding="utf-8")
        before = target.read_bytes()
        manifest, item = external_manifest(public_task(self.record), model="fake")
        for syntax_fails_first in (True, False):
            with self.subTest(syntax_fails_first=syntax_fails_first):
                client = FakeClient()
                valid_response = client.responses[-1]
                invalid = json.loads(valid_response[0])
                invalid["replacement"] = "return (x + y) / 2\n"
                syntax_error = (json.dumps(invalid), [])
                if syntax_fails_first:
                    client.responses.insert(2, syntax_error)
                else:
                    client.responses[2:] = [("", []), syntax_error, valid_response]

                record = run_episode(item=item, manifest=manifest, root=workspace,
                                     client=client, model="fake", provenance={})

                self.assertEqual(len(client.requests), 4)
                self.assertEqual(record["proposal_protocol"]["attempted"], 2)
                self.assertEqual(target.read_bytes(), before)
                first, second = record["proposal_attempts"]
                if syntax_fails_first:
                    self.assertTrue(first["valid"])
                    self.assertEqual(first["static_review"]["code"], "python_syntax_invalid")
                    feedback = client.requests[-1]["messages"][-1]["content"]
                    self.assertIn("python_syntax_invalid at Python line 2", feedback)
                    self.assertIn("2:     return (x + y) // 2", feedback)
                    self.assertTrue(second["static_review"]["passed"])
                    self.assertIn("+    return (x + y) / 2\n", record["proposal_diff"])
                else:
                    self.assertFalse(first["valid"])
                    self.assertEqual(second["static_review"]["code"], "python_syntax_invalid")
                    self.assertEqual(record["error"], "ProposalContractError: python_syntax_invalid")
                    self.assertIsNone(record["proposal_diff"])

    def test_ranged_read_feedback_recovers_once_with_original_call_id(self):
        workspace = self.prepare()
        public = public_task(self.record)
        bad_read = (None, [("read_file", {
            "path": "calculator.py", "start_line": "1", "end_line": "150",
        })])
        corrected = (None, [("read_file_range", {
            "path": "calculator.py", "start_line": 1, "end_line": 2,
        })])
        for enabled, followup in ((False, corrected), (True, corrected), (True, bad_read)):
            with self.subTest(enabled=enabled, followup=followup):
                manifest, item = external_manifest(public, model="fake", tool_call_recovery=enabled)
                client = FakeClient()
                client.responses[:1] = [bad_read, followup]
                record = run_episode(item=item, manifest=manifest, root=workspace,
                                     client=client, model="fake", provenance={})

                kinds = [event["kind"] for event in record["trajectory"]]
                self.assertEqual(kinds.count("ranged_read_feedback"), int(enabled))
                if enabled:
                    error_reply = client.requests[1]["messages"][-1]
                    self.assertEqual(error_reply["role"], "tool")
                    self.assertEqual(error_reply["tool_call_id"], "call-1")
                    self.assertIn("1-60 lines", json.loads(error_reply["content"])["hint"])
                    self.assertTrue(record["tool_call_recovery"])
                if enabled and followup == corrected:
                    self.assertIn("ranged_read_recovered", kinds)
                    self.assertIsNotNone(record["proposal_diff"])
                    self.assertEqual(record["usage"]["tool_calls"], 2)
                    self.assertEqual(record["usage"]["invalid_tool_calls"], 1)
                else:
                    self.assertEqual(record["outcome"]["status"], "protocol_error")
                    self.assertEqual(len(client.requests), 2 if enabled else 1)
                    self.assertEqual(record["observed_paths"], [])
                    self.assertIsNone(record["proposal_diff"])

    def test_export_preserves_a_missing_final_newline(self):
        target = self.original / "calculator.py"
        target.write_bytes(b"def average(x, y):\n    return x - y")
        _test_helpers.git(["commit", "-qam", "Remove final newline"], self.original)
        self.record["base_commit"] = _test_helpers.git(["rev-parse", "HEAD"], self.original)
        workspace = self.prepare()
        public = public_task(self.record)
        manifest, item = external_manifest(public, model="fake")
        client = FakeClient()
        proposal = json.loads(client.responses[-1][0])
        proposal["replacement"] = proposal["replacement"].rstrip("\n")
        client.responses[-1] = (json.dumps(proposal), [])
        record = run_episode(item=item, manifest=manifest, root=workspace,
                             client=client, model="fake", provenance={})

        prediction = validate_and_export_prediction(workspace, record, model="fake")
        patch = json.loads(prediction.read_text())["model_patch"]
        self.assertEqual(patch.count("\\ No newline at end of file"), 2)
        patch_file = workspace / "proposed.diff"
        patch_file.write_text(patch, encoding="utf-8")
        with temporary_repo(workspace / "repo") as working:
            _test_helpers.git(["apply", str(patch_file)], working)
            self.assertEqual((working / "calculator.py").read_bytes(),
                             b"def average(x, y):\n    return (x + y) / 2")

    def test_inventory_preview_reaches_model_without_restricting_read_access(self):
        workspace = self.prepare()
        (workspace / "repo" / "aaa.py").write_text("value = 1\n", encoding="utf-8")
        manifest, item = external_manifest(public_task(self.record), model="fake",
                                           file_inventory_limit=1)
        client = FakeClient()
        client.responses.insert(0, (None, [("list_files", {})]))
        record = run_episode(item=item, manifest=manifest, root=workspace,
                             client=client, model="fake", provenance={})
        shown = json.loads(next(message["content"] for message in client.requests[1]["messages"]
                                if message["role"] == "tool"))
        self.assertEqual(shown["files"], ["aaa.py"])
        self.assertGreater(shown["total_files"], 1)
        self.assertTrue(shown["truncated"])
        self.assertIn("search_code", shown["hint"])
        self.assertEqual(record["proposal"]["path"], "calculator.py")
        self.assertEqual(record["budgets"]["file_inventory_limit"], 1)
        self.assertTrue(record["experiment_id"].endswith("_inventory_1"))

    def test_larger_reserve_hands_off_to_proposal_before_an_extra_search(self):
        workspace = self.prepare()
        manifest, item = external_manifest(public_task(self.record), model="fake",
                                           proposal_reserve_tokens=6000)
        client = FakeClient()
        client.responses.pop(1)
        original_create = client.create

        def create(**kwargs):
            response = original_create(**kwargs)
            if "tools" in kwargs:
                response.usage.prompt_tokens = 10342
            return response

        client.chat.completions.create = create
        record = run_episode(item=item, manifest=manifest, root=workspace,
                             client=client, model="fake", provenance={})
        self.assertEqual(len(client.requests), 2)
        self.assertNotIn("tools", client.requests[1])
        self.assertTrue(record["proposal_attempts"][0]["valid"])
        self.assertEqual(record["budgets"]["soft_total_token_budget"], 16000)
        self.assertTrue(record["experiment_id"].endswith("_reserve_6000"))

    def test_behavioral_prompt_changes_only_proposal_system_message(self):
        workspace = self.prepare()
        runs = []
        for enabled in (False, True):
            manifest, item = external_manifest(public_task(self.record), model="fake",
                                               behavioral_proposal=enabled)
            client = FakeClient()
            client.responses.insert(2, ("", []))
            record = run_episode(item=item, manifest=manifest, root=workspace,
                                 client=client, model="fake", provenance={})
            runs.append((client.requests, record))
        (baseline, baseline_record), (candidate, candidate_record) = runs
        self.assertEqual(candidate[:2], baseline[:2])
        for proposal, control in zip(candidate[2:], baseline[2:], strict=True):
            self.assertEqual(proposal["messages"][1:], control["messages"][1:])
            self.assertIn("desired behavior", proposal["messages"][0]["content"])
        self.assertEqual(baseline_record["budgets"], candidate_record["budgets"])
        self.assertNotIn("behavioral_proposal", baseline_record["provenance"]["generation"])
        self.assertTrue(candidate_record["provenance"]["generation"]["behavioral_proposal"])
        self.assertTrue(candidate_record["proposal_attempts"][-1]["valid"])
