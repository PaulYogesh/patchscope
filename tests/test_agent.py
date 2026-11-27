import json
from pathlib import Path
from types import SimpleNamespace as NS


from patchscope.agent import run_episode
from patchscope.experiment import load_manifest, build_schedule
from patchscope.protocol import TOOL_MODE_NATIVE_REQUIRED

ROOT = Path(__file__).resolve().parents[1]


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.received.append(kwargs)
        if not self.responses:
            raise AssertionError("Unexpected extra model call")
        content, calls = self.responses.pop(0)
        native = [NS(id=f"c-{len(self.received)}", type="function",
                     function=NS(name=name, arguments=json.dumps(args)))
                  for name, args in calls]
        msg = NS(content=content, tool_calls=native)
        return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=100, completion_tokens=20))


def prepare(condition="native"):
    manifest = load_manifest(ROOT / "experiments" / "pilot_v02.json")
    item = next(i for i in build_schedule(manifest) if i["condition"] == condition)
    return manifest, item


def test_agent_native_exploration_and_proposal_without_running_code():
    manifest, item = prepare("native")
    client = FakeResponses([
        (None, [("read_file", {"path": "calculator.py"})]),
        ("Enough evidence.", []),
        (json.dumps({"path": "calculator.py",
                     "old": "return sum(values) // len(values)",
                     "new": "return sum(values) / len(values)"}), []),
    ])
    before = (ROOT / "fixtures" / "mini_repo" / "calculator.py").read_bytes()
    record = run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                         model="fake-native", provenance={}, allow_trusted_execution=False)
    assert record["outcome"]["status"] == "proposal_requires_explicit_verification_opt_in"
    assert record["outcome"]["repair_verified"] is False
    assert record["usage"]["model_calls"] == 3
    assert record["usage"]["prompt_tokens"] == 300
    assert record["usage"]["completion_tokens"] == 60
    assert record["usage"]["tool_calls"] == 1
    assert record["proposal"]["new"] == "return sum(values) / len(values)"
    assert (ROOT / "fixtures" / "mini_repo" / "calculator.py").read_bytes() == before
    assert client.received[0]["seed"] == client.received[2]["seed"]
    assert any(event["kind"] == "tool_result" for event in record["trajectory"])
    assert json.loads(json.dumps(record)) == record


def test_agent_detects_primary_text_tool_violation():
    manifest, item = prepare("native")
    client = FakeResponses([('{ "name": "read_file", "arguments": {"path": "calculator.py"} }', [])])
    record = run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                         model="fake-native", provenance={}, tool_mode=TOOL_MODE_NATIVE_REQUIRED)
    assert record["outcome"]["status"] == "protocol_error"
    assert record["usage"]["invalid_tool_calls"] == 1
    assert record["usage"]["model_calls"] == 1
    assert any(e["kind"] == "protocol_error" for e in record["trajectory"])


def test_oracle_proposal_directly_without_tool_calls():
    manifest, item = prepare("oracle")
    client = FakeResponses([
        ("I have located the bug.", []),
        (json.dumps({"path": "calculator.py", "old": "return sum(values) // len(values)",
                     "new": "return sum(values) / len(values)"}), []),
    ])
    record = run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                         model="fake-native", provenance={})
    assert record["proposal"] is not None
    assert record["usage"]["model_calls"] == 2
    assert record["usage"]["tool_calls"] == 0


def test_simulated_agent_executes_trusted_fixture_only_by_opt_in():
    manifest, item = prepare("oracle")
    client = FakeResponses([
        ("I have located the bug.", []),
        (json.dumps({"path": "calculator.py", "old": "return sum(values) // len(values)",
                     "new": "return sum(values) / len(values)"}), []),
    ])
    # NOTE: fake model response is static and trusted in this test.
    record = run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                         model="fake-native", provenance={}, allow_trusted_execution=True)
    assert record["outcome"]["status"] == "resolved"
    assert record["verification"] == {"baseline_passed": False, "patched_passed": True}


def test_model_does_not_receive_gold_task_metadata():
    manifest, item = prepare("native")
    client = FakeResponses([("No source available.", [])])
    run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                model="fake", provenance={})
    first_prompt = client.received[0]["messages"][1]["content"]
    assert "oracle" not in first_prompt.lower()
    assert "placebo_pool" not in first_prompt
    assert "calculator.py" not in first_prompt


def test_partly_seeded_file_can_be_expanded_by_read_tool():
    from patchscope.agent import _tool_result
    # The initially injected evidence contains only part of a source file.
    repo = ROOT / "fixtures" / "mini_repo"
    observed = {"calculator.py": "def average"}
    action = NS(name="read_file", arguments={"path": "calculator.py"})
    result, repeated, valid = _tool_result(repo, action, observed)
    assert valid and not repeated
    assert result["expanded_from_seed"] is True
    assert "return sum(values) // len(values)" in observed["calculator.py"]
    repeated_result, repeated, valid = _tool_result(repo, action, observed)
    assert repeated and valid and repeated_result["already_provided"]
