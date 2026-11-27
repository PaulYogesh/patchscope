"""SWE-bench Lite *development* adapter with strict agent/evaluator separation.

Only exports the public issue, repo ID, and immutable base commit. Reference
patches, test patches, labels, and hindsight hints never enter the workspace.
No repository code is executed by this module.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

DATASET = "princeton-nlp/SWE-bench_Lite"
FULL_DEV_DATASET = "SWE-bench/SWE-bench"
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
INSTANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
PUBLIC_KEYS = ("instance_id", "repo", "base_commit", "problem_statement")


class BenchmarkAdapterError(ValueError):
    pass


def public_task(row: dict[str, Any]) -> dict[str, str]:
    """Explicit allowlist: never serialize the benchmark's evaluator-only fields."""
    if not isinstance(row, dict):
        raise BenchmarkAdapterError("Task record must be a mapping")
    result = {key: row.get(key) for key in PUBLIC_KEYS}
    if not all(isinstance(v, str) and v.strip() for v in result.values()):
        raise BenchmarkAdapterError("Missing public task fields")
    if not INSTANCE_RE.fullmatch(result["instance_id"]):
        raise BenchmarkAdapterError("Unsafe instance_id")
    if not GITHUB_REPO_RE.fullmatch(result["repo"]):
        raise BenchmarkAdapterError("Unsafe GitHub repository identifier")
    if not SHA_RE.fullmatch(result["base_commit"]):
        raise BenchmarkAdapterError("Invalid 40-digit base commit")
    if len(result["problem_statement"]) > 100_000:
        raise BenchmarkAdapterError("Issue text exceeds pilot limit")
    return result


def dev_rows() -> list[dict]:
    """Download only development data; don't automatically touch the test split."""
    from datasets import load_dataset
    dataset = load_dataset(DATASET, split="dev")
    return [dict(row) for row in dataset]


def find_dev_row(instance_id: str) -> dict:
    matches = [row for row in dev_rows() if row.get("instance_id") == instance_id]
    if len(matches) != 1:
        raise BenchmarkAdapterError(f"Expected exactly one dev instance: {instance_id}")
    return matches[0]


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    command = ["git", *args]
    cp = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if cp.returncode:
        raise BenchmarkAdapterError(f"Git operation failed ({command[1]}): {cp.stderr[-800:]}")
    return cp.stdout.strip()


def prepare_dev_instance(
    row: dict, workspace_root: Path, *, clone_source: str | Path | None = None,
) -> Path:
    """Prepare immutable historical checkout without executing repo code.

    clone_source is an injectable source for offline unit tests. The public CLI
    never takes this argument and clones only the validated GitHub repository.
    """
    public = public_task(row)
    workspace_root = Path(workspace_root).expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    destination = workspace_root / public["instance_id"]
    if destination.exists():
        raise BenchmarkAdapterError(f"Workspace already exists, refusing overwrite: {destination}")
    destination.mkdir()
    repo = destination / "repo"
    source = str(clone_source) if clone_source is not None else f"https://github.com/{public['repo']}.git"
    try:
        cmd = ["clone", "--no-checkout"]
        if clone_source is None:
            cmd += ["--filter=blob:none"]
        _run_git([*cmd, source, str(repo)])
        _run_git(["checkout", "--detach", public["base_commit"]], cwd=repo)
        current = _run_git(["rev-parse", "HEAD"], cwd=repo)
        if current.lower() != public["base_commit"].lower():
            raise BenchmarkAdapterError("Checked out SHA does not match the base commit")
        (destination / "public_task.json").write_text(
            json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (destination / "issue.md").write_text(public["problem_statement"], encoding="utf-8")
    except BaseException:
        # If a clone failed, do not leave an apparently usable workspace behind.
        import shutil
        shutil.rmtree(destination)
        raise
    return destination


def load_prepared(workspace: Path) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    public = public_task(json.loads((workspace / "public_task.json").read_text(encoding="utf-8")))
    if not (workspace / "repo" / ".git").is_dir():
        raise BenchmarkAdapterError("Missing checked-out Git repository")
    sha = _run_git(["rev-parse", "HEAD"], cwd=workspace / "repo")
    if sha.lower() != public["base_commit"].lower():
        raise BenchmarkAdapterError("Repository HEAD differs from the benchmark base commit")
    if _run_git(["status", "--porcelain", "--untracked-files=no"], cwd=workspace / "repo"):
        raise BenchmarkAdapterError("Tracked repository files changed; refusing benchmark run")
    if _run_git(["ls-files", "--others", "-z", "--", "*.py"], cwd=workspace / "repo"):
        raise BenchmarkAdapterError("Untracked Python files found; refusing benchmark run")
    if (workspace / "issue.md").read_bytes().decode("utf-8") != public["problem_statement"]:
        raise BenchmarkAdapterError("Issue file changed from original public task")
    return public


def external_manifest(
    public: dict, *, model: str, max_steps: int = 10, proposal_reasoning_effort: str | None = None,
    file_inventory_limit: int | None = None, proposal_reserve_tokens: int | None = None,
    behavioral_proposal: bool = False, tool_call_recovery: bool = False,
    matched_source: bool = False,
) -> tuple[dict, dict]:
    """Reuse existing run_episode with native evidence, and execution disabled.

    No gold locations, no placebo pool, no hidden tests, no test commands.
    These are new external-pilot settings; never compare their tokens directly
    to old v0.6 runs as if the protocols were identical.
    """
    public = public_task(public)
    task = {
        "task_id": public["instance_id"],
        "repo_path": "repo",
        "issue_path": "issue.md",
        "trusted_execution": False,
        "verification": {"kind": "not_executed"},
        "oracle": {"paths": []},
        "placebo_pool": [],
    }
    manifest = {
        "schema_version": 1,
        "experiment_id": "swebench_lite_dev_v09",
        "conditions": ["native"],
        "model": {"primary": model, "temperature": 0},
        "retrieval": {"top_k": 1},
        "evidence_policy": "off",
        "repo_tools_policy": "navigation_v1",
        "proposal_contract": "line_range_hash_v1",
        "operative_trace_policy": "off",
        "budgets": {
            "max_steps": max_steps,
            "max_tool_calls": max_steps + 2,
            "max_model_calls": max_steps + 4,
            "max_completion_tokens_per_call": 450,
            "max_patch_completion_tokens_per_call": 1600,
            "soft_total_token_budget": 16000,
            "proposal_reserve_tokens": 4500,
            "seed_char_budget": 1600,
            "max_patch_retries": 1,
        },
        "tasks": [task],
    }
    if proposal_reasoning_effort is not None:
        manifest["model"]["proposal_reasoning_effort"] = proposal_reasoning_effort
        manifest["experiment_id"] += f"_proposal_reasoning_{proposal_reasoning_effort}"
    if file_inventory_limit is not None:
        if type(file_inventory_limit) is not int or file_inventory_limit < 1:
            raise BenchmarkAdapterError("File inventory limit must be a positive integer")
        manifest["budgets"]["file_inventory_limit"] = file_inventory_limit
        manifest["experiment_id"] += f"_inventory_{file_inventory_limit}"
    if proposal_reserve_tokens is not None:
        if (type(proposal_reserve_tokens) is not int
                or not 0 < proposal_reserve_tokens < manifest["budgets"]["soft_total_token_budget"]):
            raise BenchmarkAdapterError("Proposal reserve must be positive and below the soft total budget")
        manifest["budgets"]["proposal_reserve_tokens"] = proposal_reserve_tokens
        manifest["experiment_id"] += f"_reserve_{proposal_reserve_tokens}"
    if behavioral_proposal:
        manifest["model"]["behavioral_proposal"] = True
        manifest["experiment_id"] += "_behavioral_proposal"
    if tool_call_recovery:
        manifest["tool_call_recovery"] = True
        manifest["experiment_id"] += "_tool_call_recovery"
    if matched_source:
        manifest["matched_source"] = True
        manifest["experiment_id"] += "_matched_source"
    item = {
        "task": task,
        "task_id": public["instance_id"],
        "condition": "native",
        "repetition": 0,
        "model_seed": 62000,
        "block_seed": 20261103,
    }
    return manifest, item


def validate_and_export_prediction(workspace: Path, episode: dict, *, model: str) -> Path:
    """Produce one SWE-bench JSONL record if the patch applies cleanly.

    The official Docker harness, NOT this function, determines resolution.
    """
    workspace = Path(workspace).expanduser().resolve()
    public = load_prepared(workspace)
    patch = episode.get("proposal_diff")
    proposal = episode.get("proposal")
    if not isinstance(proposal, dict) or not isinstance(patch, str) or not patch.strip():
        raise BenchmarkAdapterError("Agent did not generate a valid nonempty patch")
    path = proposal.get("path")
    from patchscope.tools import is_test_path, list_source_files

    repo = workspace / "repo"
    if not isinstance(path, str) or is_test_path(path) or path not in list_source_files(repo):
        raise BenchmarkAdapterError("Pilot permits only Python source edits")
    cp = subprocess.run(
        ["git", "apply", "--check", "--index", "--numstat", "-z", "--summary", "-"], cwd=repo,
        input=patch.encode("utf-8"), capture_output=True, check=False,
    )
    if cp.returncode != 0:
        detail = cp.stderr[-500:].decode("utf-8", errors="replace")
        raise BenchmarkAdapterError(f"Patch does not apply to base commit: {detail}")
    stats, separator, summary = cp.stdout.partition(b"\0")
    added, _, remainder = stats.partition(b"\t")
    removed, _, actual_path = remainder.partition(b"\t")
    if (not separator or summary or actual_path != path.encode("utf-8")
            or not added.isdigit() or not removed.isdigit() or not (int(added) + int(removed))):
        raise BenchmarkAdapterError("Patch must update exactly the declared Python source file")
    # A second immutable check catches unexpected writes during agent exploration.
    load_prepared(workspace)
    record = {
        "instance_id": public["instance_id"],
        "model_name_or_path": model,
        "model_patch": patch,
    }
    dest = workspace / "prediction.jsonl"
    try:
        with dest.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except FileExistsError as exc:
        raise BenchmarkAdapterError(f"Prediction already exists: {dest}") from exc
    return dest


def save_episode_prediction(workspace: Path, record: dict, *, model: str) -> Path | None:
    """Persist the episode before attempting to export its proposed diff."""
    output = workspace / "episode.json"
    with output.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    if not record.get("proposal_diff"):
        return None
    try:
        return validate_and_export_prediction(workspace, record, model=model)
    except BenchmarkAdapterError as exc:
        (workspace / "prediction_export_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
        return None


def run_local_pilot(
    workspace: Path, *, model: str, max_steps: int = 10, proposal_reasoning_effort: str | None = None,
    file_inventory_limit: int | None = None, proposal_reserve_tokens: int | None = None,
    behavioral_proposal: bool = False, tool_call_recovery: bool = False,
    matched_source: bool = False, benchmark: str = DATASET,
) -> tuple[dict, Path | None]:
    """Call ORIGINAL PatchScope run_episode, with host test execution disabled."""
    from openai import OpenAI
    from patchscope.agent import run_episode
    from patchscope.llm import get_config
    from patchscope.protocol import TOOL_MODE_NATIVE_REQUIRED

    workspace = Path(workspace).expanduser().resolve()
    if (workspace / "episode.json").exists():
        raise BenchmarkAdapterError("Existing episode found. Use another workspace")
    public = load_prepared(workspace)
    manifest, item = external_manifest(
        public, model=model, max_steps=max_steps, proposal_reasoning_effort=proposal_reasoning_effort,
        file_inventory_limit=file_inventory_limit,
        proposal_reserve_tokens=proposal_reserve_tokens,
        behavioral_proposal=behavioral_proposal, tool_call_recovery=tool_call_recovery,
        matched_source=matched_source,
    )
    if benchmark not in {DATASET, FULL_DEV_DATASET}:
        raise BenchmarkAdapterError("Unsupported development dataset")
    if benchmark == FULL_DEV_DATASET:
        manifest["experiment_id"] = manifest["experiment_id"].replace("swebench_lite_", "swebench_full_", 1)
    config = get_config()
    client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=180, max_retries=0)
    record = run_episode(
        item=item, manifest=manifest, root=workspace, client=client, model=model,
        provenance={
            "benchmark": benchmark,
            "split": "dev",
            "base_commit": public["base_commit"],
            "public_issue_sha256": hashlib.sha256(public["problem_statement"].encode()).hexdigest(),
            "grader_status": "not_run",
        },
        allow_trusted_execution=False,
        tool_mode=TOOL_MODE_NATIVE_REQUIRED,
    )
    return record, save_episode_prediction(workspace, record, model=model)
