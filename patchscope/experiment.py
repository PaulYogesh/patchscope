"""Experiment manifest validation and paired deterministic scheduling."""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from patchscope.interventions import CONDITIONS
from patchscope.tools import list_source_files

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$")


def _within(root: Path, name: str, *, must_exist=True) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f"Invalid repository-relative path: {name!r}")
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes project: {name}")
    if must_exist and not target.exists():
        raise ValueError(f"Missing path: {name}")
    return target


def manifest_sha256(manifest: dict) -> str:
    blob = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def load_manifest(path: str | Path, *, root: Path = PROJECT_ROOT) -> dict:
    """Validate a manifest against actually permitted source and test files."""
    path = Path(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported experiment manifest version")
    exp_id = manifest.get("experiment_id")
    if not isinstance(exp_id, str) or not _ID_RE.fullmatch(exp_id):
        raise ValueError("Invalid experiment_id")
    conditions = manifest.get("conditions")
    baseline = {"native", "bm25", "placebo", "oracle"}
    if (not isinstance(conditions, list) or len(conditions) != len(set(conditions))
            or not baseline <= set(conditions) or not set(conditions) <= set(CONDITIONS)):
        raise ValueError("Expected four baseline conditions, optionally plus misleading")
    for key in ("repetitions", "randomization_seed", "model_seed_base"):
        value = manifest.get(key)
        if type(value) is not int or value < (1 if key == "repetitions" else 0):
            raise ValueError(f"Invalid {key}")
    model = manifest.get("model")
    if not isinstance(model, dict) or not isinstance(model.get("primary"), str):
        raise ValueError("Model settings missing")
    budgets = manifest.get("budgets")
    if not isinstance(budgets, dict):
        raise ValueError("Budget configuration missing")
    for key in ("max_steps", "max_tool_calls", "max_model_calls", "max_completion_tokens_per_call",
                "soft_total_token_budget", "seed_char_budget"):
        if type(budgets.get(key)) is not int or budgets[key] < 1:
            raise ValueError(f"Invalid budget {key}")
    # Optional patch-only completion ceiling. Older manifests retain their
    # original exploration/patch parity for historical reproducibility.
    patch_cap = budgets.get("max_patch_completion_tokens_per_call")
    if patch_cap is not None and (type(patch_cap) is not int or not 1 <= patch_cap <= 4096):
        raise ValueError("Invalid max_patch_completion_tokens_per_call (expected 1..4096)")
    retries = budgets.get("max_patch_retries", 0)
    if type(retries) is not int or not (0 <= retries <= 2):
        raise ValueError("Invalid max_patch_retries (expected integer 0..2)")
    # Public executable reproduction is separate from the held-out evaluator.
    # Old manifests default to no trace and retain identical behavior.
    trace_policy = manifest.get("operative_trace_policy", "off")
    if trace_policy not in {"off", "public_reproducer"}:
        raise ValueError("Invalid operative_trace_policy")
    if trace_policy == "public_reproducer":
        if not all(isinstance(t, dict) and t.get("trusted_execution") is True
                   and isinstance(t.get("public_reproducer_path"), str)
                   for t in manifest["tasks"]):
            raise ValueError("Public trace requires trusted tasks and declared reproducers")
    evidence_policy = manifest.get("evidence_policy", "off")
    if evidence_policy not in {"off", "inventory", "imports"}:
        raise ValueError("Invalid evidence_policy")
    source_map_chars = budgets.get("source_map_char_budget", 1400)
    if type(source_map_chars) is not int or not 300 <= source_map_chars <= 2400:
        raise ValueError("Invalid source_map_char_budget (expected 300..2400)")
    if budgets["seed_char_budget"] < 40:
        raise ValueError("Seed budget too small")
    retrieval = manifest.get("retrieval")
    if not isinstance(retrieval, dict) or type(retrieval.get("top_k")) is not int or retrieval["top_k"] < 1:
        raise ValueError("Invalid retrieval configuration")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Manifest requires at least one task")
    seen = set()
    root = root.resolve()
    for task in tasks:
        task_id = task.get("task_id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not _ID_RE.fullmatch(task_id) or task_id in seen:
            raise ValueError(f"Invalid or duplicate task_id: {task_id!r}")
        seen.add(task_id)
        repo = _within(root, task.get("repo_path", ""))
        if not repo.is_dir():
            raise ValueError(f"Not a repository directory: {repo}")
        issue_path = _within(root, task.get("issue_path", ""))
        if not issue_path.is_file() or not issue_path.is_relative_to(repo):
            raise ValueError(f"Issue must belong to task repository: {task_id}")
        approved = set(list_source_files(repo))
        oracle = task.get("oracle") or {}
        oracle_paths = oracle.get("paths")
        placebo = task.get("placebo_pool")
        misleading = task.get("misleading_pool")
        if not isinstance(oracle_paths, list) or not oracle_paths or not set(oracle_paths) <= approved:
            raise ValueError(f"Invalid oracle source paths: {task_id}")
        if not isinstance(placebo, list) or not placebo or not set(placebo) <= approved:
            raise ValueError(f"Invalid placebo source paths: {task_id}")
        if set(oracle_paths) & set(placebo):
            raise ValueError(f"Oracle/placebo overlap: {task_id}")
        if "misleading" in conditions:
            if (not isinstance(misleading, list) or not misleading
                    or len(misleading) != len(set(misleading))
                    or not set(misleading) <= approved):
                raise ValueError(f"Invalid misleading source paths: {task_id}")
            if set(misleading) & (set(oracle_paths) | set(placebo)):
                raise ValueError(f"Misleading/oracle/placebo overlap: {task_id}")
        if trace_policy == "public_reproducer":
            public_script = _within(root, task["public_reproducer_path"])
            if (not public_script.is_file() or public_script.suffix != ".py"
                    or public_script.is_relative_to(repo)
                    or not public_script.is_relative_to(root / "reproducers")):
                raise ValueError(f"Invalid separate public reproducer: {task_id}")
        verification = task.get("verification")
        if not isinstance(verification, dict) or verification.get("kind") != "pytest":
            raise ValueError(f"Unsupported verifier: {task_id}")
        timeout = verification.get("timeout_seconds")
        if type(timeout) is not int or not 1 <= timeout <= 300:
            raise ValueError("Invalid test timeout")
        if type(task.get("trusted_execution")) is not bool:
            raise ValueError("trusted_execution must be an explicit boolean")
    return manifest


def stable_seed(base: int, task_id: str, repetition: int) -> int:
    blob = f"{base}:{task_id}:{repetition}".encode()
    return (base + int.from_bytes(hashlib.sha256(blob).digest()[:4], "big")) % (2**31 - 1)


def build_schedule(manifest: dict) -> list[dict]:
    schedule = []
    for task in manifest["tasks"]:
        for repetition in range(manifest["repetitions"]):
            block_seed = stable_seed(manifest["randomization_seed"], task["task_id"], repetition)
            model_seed = stable_seed(manifest["model_seed_base"], task["task_id"], repetition)
            conditions = list(manifest["conditions"])
            random.Random(block_seed).shuffle(conditions)
            for condition in conditions:
                schedule.append({
                    "task": task, "task_id": task["task_id"],
                    "condition": condition, "repetition": repetition,
                    "model_seed": model_seed, "block_seed": block_seed,
                })
    return schedule


def run_id(item: dict) -> str:
    return f"{item['task_id']}__{item['condition']}__r{item['repetition']:02d}"
