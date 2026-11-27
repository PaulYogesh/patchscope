import json
from pathlib import Path
from types import SimpleNamespace as NS

from patchscope.agent import run_episode
from patchscope.experiment import load_manifest, build_schedule
from patchscope.failure_triage import error_category

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if not self.replies:
            raise AssertionError("Unplanned call")
        txt = self.replies.pop(0)
        return NS(choices=[NS(message=NS(content=txt, tool_calls=[]), finish_reason="stop")],
                  usage=NS(prompt_tokens=120, completion_tokens=35))


def setup():
    manifest = load_manifest(ROOT / "experiments/repair_diagnostic_v023.json")
    item = next(x for x in build_schedule(manifest)
                if x["task_id"] == "mini-average-001" and x["condition"] == "oracle")
    valid = json.dumps({"path": "calculator.py", "old": "return sum(values) // len(values)",
                        "new": "return sum(values) / len(values)"})
    return manifest, item, valid


def test_invalid_json_recovery_without_source_or_verification_mutation():
    manifest, item, valid = setup()
    before = (ROOT / "fixtures/mini_repo/calculator.py").read_bytes()
    client = FakeClient(["Found it", "The fix is to change // to /", valid])
    r = run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                    model="fake", provenance={}, allow_trusted_execution=False)
    assert r["outcome"]["status"] == "proposal_requires_explicit_verification_opt_in"
    assert [a["valid"] for a in r["proposal_attempts"]] == [False, True]
    assert r["proposal_attempts"][0]["reason"] == "patch_json_invalid_or_missing"
    assert r["usage"]["model_calls"] == 3
    assert r["usage"]["total_tokens"] == 465
    assert r["usage"]["usage_events"][-1]["purpose"] == "patch_contract_retry"
    assert r["usage"]["usage_events"][-1]["finish_reason"] == "stop"
    assert client.calls[-1]["messages"][-1]["role"] == "user"
    assert "patch_json_invalid_or_missing" in client.calls[-1]["messages"][-1]["content"]
    assert (ROOT / "fixtures/mini_repo/calculator.py").read_bytes() == before


def test_failure_after_single_retry_stays_failure():
    manifest, item, _ = setup()
    r = run_episode(item=item, manifest=manifest, root=ROOT,
                    client=FakeClient(["Ready", "not json", '{"oops": 1}']),
                    model="fake", provenance={})
    assert r["outcome"]["status"] == "error"
    assert r["proposal"] is None
    assert [a["reason"] for a in r["proposal_attempts"]] == [
        "patch_json_invalid_or_missing", "patch_fields_invalid"]
    assert error_category(r) == "patch_contract_validation"


def test_old_manifest_defaults_to_zero_retries():
    manifest, item, valid = setup()
    manifest["budgets"].pop("max_patch_retries")
    r = run_episode(item=item, manifest=manifest, root=ROOT,
                    client=FakeClient(["Ready", "not json"]),
                    model="fake", provenance={})
    assert r["outcome"]["status"] == "error"
    assert r["usage"]["model_calls"] == 2
    assert r["proposal_protocol"]["max_patch_retries"] == 0


def test_new_repair_can_be_verified_but_requires_optin():
    manifest, item, valid = setup()
    r = run_episode(item=item, manifest=manifest, root=ROOT,
                    client=FakeClient(["Ready", "not json", valid]),
                    model="fake", provenance={}, allow_trusted_execution=True)
    assert r["outcome"]["status"] == "resolved"
    assert r["verification"] == {"baseline_passed": False, "patched_passed": True}
