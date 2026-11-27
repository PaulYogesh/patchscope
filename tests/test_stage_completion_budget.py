"""Stage-specific completion budgets and transparent proposal diagnostics."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from patchscope.agent import run_episode
from patchscope.experiment import build_schedule, load_manifest
from patchscope.proposal_audit import audit_proposals, render_proposal_audit

ROOT = Path(__file__).resolve().parents[1]


class ScriptedClient:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.scripted:
            raise AssertionError("unexpected call")
        content, tokens, reason = self.scripted.pop(0)
        return NS(
            choices=[NS(message=NS(content=content, tool_calls=[]), finish_reason=reason)],
            usage=NS(prompt_tokens=100, completion_tokens=tokens),
        )


def _setup():
    manifest = load_manifest(ROOT / "experiments/proposal_cap_v024.json")
    item = next(x for x in build_schedule(manifest)
                if x["task_id"] == "mini-slug-003" and x["condition"] == "oracle")
    return manifest, item


def test_v024_only_changes_proposal_ceiling_and_has_unique_id():
    old = load_manifest(ROOT / "experiments/repair_diagnostic_v023.json")
    new = load_manifest(ROOT / "experiments/proposal_cap_v024.json")
    assert new["experiment_id"] != old["experiment_id"]
    assert old["budgets"].get("max_patch_completion_tokens_per_call") is None
    assert new["budgets"]["max_patch_completion_tokens_per_call"] == 1400
    assert new["budgets"]["max_completion_tokens_per_call"] == 450
    assert new["budgets"]["max_patch_retries"] == old["budgets"]["max_patch_retries"]
    assert new["budgets"]["soft_total_token_budget"] == old["budgets"]["soft_total_token_budget"]
    assert new["randomization_seed"] == old["randomization_seed"]
    assert new["model_seed_base"] == old["model_seed_base"]
    assert len(build_schedule(new)) == 16


def test_separate_patch_cap_and_full_diagnostics():
    manifest, item = _setup()
    # First model reply finishes exploration. Patch exhausts new budget and is
    # rejected. The correction is valid. No actual generated code execution.
    good = json.dumps({"path": "text_ops.py",
                       "old": 'return text.lower().strip().replace(" ", "-")',
                       "new": 'return "-".join(text.lower().split())'})
    client = ScriptedClient([("Source found", 20, "stop"),
                             ("{", 1400, "length"),
                             (good, 140, "stop")])
    result = run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                         model="fake", provenance={}, allow_trusted_execution=False)
    assert result["outcome"]["status"] == "proposal_requires_explicit_verification_opt_in"
    assert [call["max_tokens"] for call in client.calls] == [450, 1400, 1400]
    assert [e["requested_max_tokens"] for e in result["usage"]["usage_events"]] == [450, 1400, 1400]
    assert result["proposal_attempts"][0]["reason"] == "patch_json_invalid_or_missing"
    assert result["proposal_attempts"][0]["at_completion_cap"] is True
    assert result["proposal_attempts"][0]["finish_reason_length"] is True
    assert result["proposal_attempts"][0]["response_chars"] == 1
    assert result["proposal_attempts"][1]["at_completion_cap"] is False
    report = audit_proposals([result])
    assert report["groups"][0]["at_completion_ceiling"] is True
    rendered = render_proposal_audit(report)
    assert "1400 / 1400" in rendered
    assert "length" in rendered
    assert "patch_json_invalid_or_missing" in rendered
    assert "join(text.lower().split())" not in rendered


def test_old_manifest_keeps_450_limit_for_proposals():
    manifest, item = _setup()
    manifest = copy.deepcopy(manifest)
    del manifest["budgets"]["max_patch_completion_tokens_per_call"]
    good = json.dumps({"path": "text_ops.py",
                       "old": 'return text.lower().strip().replace(" ", "-")',
                       "new": 'return "-".join(text.lower().split())'})
    client = ScriptedClient([("Located", 10, "stop"), (good, 120, "stop")])
    run_episode(item=item, manifest=manifest, root=ROOT, client=client,
                model="fake", provenance={})
    assert [call["max_tokens"] for call in client.calls] == [450, 450]


@pytest.mark.parametrize("bad", [-1, 0, "1400", True, 5000])
def test_reject_invalid_patch_budget(tmp_path, bad):
    manifest, _ = _setup()
    manifest["budgets"]["max_patch_completion_tokens_per_call"] = bad
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="max_patch_completion_tokens_per_call"):
        load_manifest(path)
