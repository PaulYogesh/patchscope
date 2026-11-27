"""Frozen proposal experiments must not silently inject unseen source evidence."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from patchscope.experiment import build_schedule, load_manifest
from patchscope.frozen_replay import (
    frozen_observations, propose_frozen, compare_frozen,
    render_frozen,
)
from patchscope.source_map import POLICIES
from patchscope.tools import read_source_file

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return NS(choices=[NS(message=NS(content=self.response), finish_reason="stop")],
                  usage=NS(prompt_tokens=110, completion_tokens=80))


def source():
    manifest = load_manifest(ROOT / "experiments/interference_smoke_v030.json")
    item = next(x for x in build_schedule(manifest)
                if x["task_id"] == "mini-average-001" and x["condition"] == "native")
    task = item["task"]
    repo = ROOT / task["repo_path"]
    issue = (ROOT / task["issue_path"]).read_text(encoding="utf-8")
    content = read_source_file(repo, "calculator.py", max_chars=2000)
    rec = {
        "experiment_id": manifest["experiment_id"], "task_id": task["task_id"],
        "condition": "native", "run_id": "mini-average-001__native__r00",
        "repetition": 0, "outcome": {"status": "resolved", "repair_verified": True},
        "intervention": {"sources": []},
        "transcript": [{"role": "user", "content": f"Bug report:\n{issue}\n\nLocate the faulty implementation using repository tools."}],
        "trajectory": [{"kind": "tool_result", "name": "read_file", "result": content}],
        "observed_paths": ["calculator.py"],
        "proposal": {"path": "calculator.py"},
        "provenance": {"generation": {"seed": item["model_seed"], "model": "fake"},
                       "ollama": {"digest": "test-model-sha"}},
    }
    return manifest, task, rec


def test_exact_frozen_observation_rejects_changed_content_issue_and_mismatch():
    manifest, task, rec = source()
    repo = ROOT / task["repo_path"]
    issue = (ROOT / task["issue_path"]).read_text(encoding="utf-8")
    assert list(frozen_observations(rec, repo=repo, issue=issue)) == ["calculator.py"]
    rec["trajectory"][0]["result"]["content"] += "bad"
    with pytest.raises(ValueError, match="frozen_source_content_mismatch"):
        frozen_observations(rec, repo=repo, issue=issue)
    rec["trajectory"][0]["result"]["content"] = read_source_file(repo, "calculator.py")["content"]
    with pytest.raises(ValueError, match="source_issue_mismatch"):
        frozen_observations(rec, repo=repo, issue="changed issue")
    rec["observed_paths"] = ["fake.py"]
    with pytest.raises(ValueError, match="frozen_observed_paths_mismatch"):
        frozen_observations(rec, repo=repo, issue=issue)
    rec["observed_paths"] = ["calculator.py"]
    rec["intervention"]["sources"] = [{"path": "fake.py"}]
    with pytest.raises(ValueError, match="seeded_source_not_supported"):
        frozen_observations(rec, repo=repo, issue=issue)


def test_all_policies_get_exact_same_observed_text_and_no_exploration_calls():
    manifest, task, rec = source()
    response = json.dumps({"path": "calculator.py", "old": "return sum(values) // len(values)",
                           "new": "return sum(values) / len(values)"})
    results = {}
    calls = {}
    for policy in POLICIES:
        client = FakeClient(response)
        record = propose_frozen(client=client, model="fake", policy=policy,
                                task=task, source_record=rec, source_manifest=manifest,
                                root=ROOT, provenance={"ollama": {"digest": "test-model-sha"}})
        results[policy] = record
        assert record["outcome"]["status"] == "proposal_requires_explicit_verification_opt_in"
        assert record["usage"]["model_calls"] == 1
        assert record["proposal"]["path"] == "calculator.py"
        assert record["source"]["observed_paths"] == ["calculator.py"]
        assert client.calls[0]["max_tokens"] == 1400
        assert client.calls[0]["seed"] == rec["provenance"]["generation"]["seed"]
        assert "tools" not in client.calls[0]
        calls[policy] = client.calls[0]["messages"][1]["content"]
    assert len({record["source"]["snapshot_sha256"] for record in results.values()}) == 1
    assert all("Observed source:\nFILE: calculator.py\n" in calls[p] for p in POLICIES)
    assert all("return sum(values) // len(values)" in calls[p] for p in POLICIES)
    assert calls["off"] != calls["inventory"] != calls["imports"]
    assert "Static source imports" in calls["imports"]
    assert "Static source imports" not in calls["inventory"]
    assert "Static source imports" not in calls["off"]


def test_compare_rejects_incomplete_or_snapshot_mismatch():
    manifest, task, rec = source()
    response = json.dumps({"path": "calculator.py", "old": "return sum(values) // len(values)",
                           "new": "return sum(values) / len(values)"})
    provenance = {"ollama": {"digest": "test-model-sha"}}
    arms = {}
    for policy in POLICIES:
        result = propose_frozen(client=FakeClient(response), model="fake", policy=policy,
                                task=task, source_record=rec, source_manifest=manifest,
                                root=ROOT, provenance=provenance)
        arms[policy] = {(task["task_id"], 0): result}
    summary = compare_frozen(arms)
    assert summary["n_matched"] == 1
    assert "frozen-exploration" in render_frozen(summary)
    arms["imports"][(task["task_id"], 0)]["source"]["snapshot_sha256"] = "corrupt"
    with pytest.raises(ValueError, match="frozen_replay_provenance_mismatch"):
        compare_frozen(arms)
    arms["imports"] = {}
    with pytest.raises(ValueError, match="incomplete_or_unmatched"):
        compare_frozen(arms)


def test_frozen_proposal_end_to_end_verified_on_trusted_fixture():
    manifest, task, rec = source()
    client = FakeClient(json.dumps({
        "path": "calculator.py", "old": "return sum(values) // len(values)",
        "new": "return sum(values) / len(values)"}))
    before = (ROOT / task["repo_path"] / "calculator.py").read_bytes()
    record = propose_frozen(client=client, model="fake", policy="off",
                            task=task, source_record=rec, source_manifest=manifest,
                            root=ROOT, provenance={"ollama": {"digest": "test-model-sha"}},
                            allow_trusted_execution=True)
    assert record["outcome"]["status"] == "resolved"
    assert record["verification"]["baseline_passed"] is False
    assert record["verification"]["patched_passed"] is True
    assert (ROOT / task["repo_path"] / "calculator.py").read_bytes() == before
