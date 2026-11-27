"""Run an Aider editing pass over source paths observed by a native episode."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from patchscope.proposal_source import (
    SOURCE_BYTE_LIMIT, describe_proposal_sources, read_proposal_sources,
)
from patchscope.proposal_windows import describe_replayed_spans, lift_replayed_edit
from patchscope.repair import render_repair_diff
from patchscope.static_review import review_python_edit
from patchscope.swebench_dev import (
    DATASET, BenchmarkAdapterError, load_prepared, prepare_dev_instance, save_episode_prediction,
)

AIDER_VERSION = "0.86.2"
EDITOR_TIMEOUT_SECONDS = 420


def _git(repo: Path, env: dict, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args], cwd=repo, env=env, check=True,
        text=True, capture_output=True,
    ).stdout


def _edit_source(paths: dict[str, bytes], *, issue: str, aider: Path, model: str,
                 ollama_url: str, workspace: Path, record: dict,
                 windows: dict[str, dict] | None = None) -> None:
    with TemporaryDirectory(prefix="patchscope-aider-") as directory:
        sandbox = Path(directory)
        repo = sandbox / "source"
        repo.mkdir()
        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(sandbox),
            "GIT_CONFIG_NOSYSTEM": "1",
            "OLLAMA_API_BASE": ollama_url,
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "PYTHONUTF8": "1",
        }
        for path, content in paths.items():
            dest = repo / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        _git(repo, env, "init", "-q")
        _git(repo, env, "add", "--", *paths)
        message = sandbox / "issue.txt"
        context = ""
        if windows is not None:
            descriptions = describe_replayed_spans(list(windows.values()))["files"]
            ranges = ", ".join(
                f"{item['path']} ({item['start_line']}-{item['end_line']})"
                for item in descriptions
            )
            context = f"The supplied files show excerpts from these original line ranges: {ranges}. "
        message.write_text(
            "Fix the Python behavior described in the issue. Edit just one of the "
            "supplied implementation files. Preserve unrelated behavior.\n\n"
            f"{context}Issue:\n{issue}",
            encoding="utf-8",
        )
        flags = [
            "--model", f"ollama_chat/{model}", "--edit-format", "diff",
            "--message-file", str(message), "--no-git", "--map-tokens", "0",
            "--no-auto-commits", "--no-auto-lint", "--no-auto-test",
            "--no-gitignore", "--no-add-gitignore-files",
            "--no-suggest-shell-commands", "--no-detect-urls", "--no-analytics",
            "--no-check-update", "--no-show-release-notes", "--no-stream", "--no-fancy-input",
            "--chat-history-file", str(sandbox / "chat.md"),
            "--input-history-file", str(sandbox / "input.txt"),
        ]
        start = perf_counter()
        try:
            with (workspace / "aider.log").open("xb") as log:
                process = subprocess.run(
                    [str(aider), *flags, *(f"./{path}" for path in paths)],
                    cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, timeout=EDITOR_TIMEOUT_SECONDS, check=False,
                )
        except subprocess.TimeoutExpired:
            record["outcome"]["status"] = "editor_timeout"
            return
        finally:
            record["usage"]["wall_seconds"] = round(perf_counter() - start, 3)
        if process.returncode:
            record["outcome"]["status"] = "editor_process_error"
            record["editor_exit_code"] = process.returncode
            return
        changed = _git(repo, env, "diff", "--name-only", "-z", "--").split("\0")[:-1]
        untracked = _git(repo, env, "ls-files", "--others", "-z").split("\0")[:-1]
        if untracked or len(changed) > 1 or any(path not in paths for path in changed):
            record["outcome"]["status"] = "editor_edit_out_of_scope"
            return
        if not changed:
            record["outcome"]["status"] = "editor_no_edit"
            return
        path = changed[0]
        dest = repo / path
        if (not dest.is_file() or dest.resolve() != dest or dest.stat().st_size > SOURCE_BYTE_LIMIT
                or dest.stat().st_mode & 0o111):
            record["outcome"]["status"] = "editor_edit_out_of_scope"
            return
        try:
            replacement = dest.read_bytes().decode("utf-8")
            if windows is None:
                original, edited = paths[path].decode("utf-8"), replacement
            else:
                original, edited = lift_replayed_edit(workspace / "repo", windows[path], replacement)
            review = review_python_edit(original, edited)
        except (UnicodeError, ValueError):
            record["outcome"]["status"] = "editor_edit_out_of_scope"
            return
        record["proposal"] = {"path": path}
        record["static_review"] = review
        if not review["passed"]:
            record["outcome"]["status"] = review["code"]
            return
        record["proposal_diff"] = (
            _git(repo, env, "diff", "--no-ext-diff", "--no-color", "--", path)
            if windows is None else render_repair_diff(path, original, edited)
        )
        record["outcome"]["status"] = "proposal_requires_explicit_verification_opt_in"


def run_aider_pilot(
    baseline: Path, candidate_root: Path, *, aider: Path, ollama_url: str,
) -> tuple[dict, Path | None]:
    baseline = baseline.expanduser().resolve()
    aider = aider.expanduser().resolve()
    public = load_prepared(baseline)
    episode_bytes = (baseline / "episode.json").read_bytes()
    episode = json.loads(episode_bytes)
    provenance = episode["provenance"]
    issue_hash = hashlib.sha256(public["problem_statement"].encode()).hexdigest()
    model = provenance["generation"]["model"]
    if (episode["task_id"] != public["instance_id"] or episode["condition"] != "native"
            or provenance["benchmark"] != DATASET or provenance["split"] != "dev"
            or provenance["base_commit"] != public["base_commit"]
            or provenance["public_issue_sha256"] != issue_hash
            or episode.get("tool_call_recovery") or episode.get("editor_comparator")
            or not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:-]*", model)):
        raise BenchmarkAdapterError("Baseline episode does not match the prepared native development issue")
    if not aider.is_file() or not os.access(aider, os.X_OK):
        raise BenchmarkAdapterError("Aider binary is missing or not executable")
    repo = baseline / "repo"
    matched_source = episode.get("matched_source", False)
    proposal_source = episode.get("proposal_source")
    replayed = episode.get("proposal_windows")
    windows = None
    if replayed is None:
        contents, total = read_proposal_sources(repo, episode["observed_paths"])
        if matched_source and proposal_source is not None:
            if not contents or describe_proposal_sources(contents) != proposal_source:
                raise BenchmarkAdapterError("Aider source does not match the saved native proposal inputs")
    else:
        windows = {span["path"]: span for span in replayed}
        if len(windows) != len(replayed) or (windows and describe_replayed_spans(replayed) != proposal_source):
            raise BenchmarkAdapterError("Aider windows do not match the saved native proposal inputs")
        contents = {path: span["content"].encode("utf-8") for path, span in windows.items()}
        for span in replayed:
            lift_replayed_edit(repo, span, span["content"])
        total = sum(len(content) for content in contents.values())
    destination = prepare_dev_instance(public, candidate_root, clone_source=repo)
    record = {
        "schema_version": 2, "experiment_id": "swebench_lite_dev_aider_diff",
        "task_id": public["instance_id"], "condition": "native",
        "provenance": {
            "benchmark": DATASET, "split": "dev", "base_commit": public["base_commit"],
            "public_issue_sha256": issue_hash, "generation": {"model": model},
        },
        "editor_comparator": {
            "name": "aider_diff", "version": AIDER_VERSION,
            "baseline_episode_sha256": hashlib.sha256(episode_bytes).hexdigest(),
            "evidence": "full_files_for_native_observed_paths" if windows is None else "replayed_windows_v1",
            "source_bytes": total,
        },
        "budgets": {"source_byte_limit": SOURCE_BYTE_LIMIT, "editor_timeout": EDITOR_TIMEOUT_SECONDS},
        "observed_paths": sorted(contents) if total <= SOURCE_BYTE_LIMIT else [],
        "usage": {"total_tokens": None, "wall_seconds": None},
        "proposal": None, "proposal_diff": None, "static_review": None,
        "outcome": {"status": "editor_no_observed_source", "repair_verified": False},
    }
    if matched_source:
        record.update(matched_source=True, proposal_source=proposal_source)
    if matched_source and proposal_source is None:
        record["outcome"]["status"] = "editor_no_shared_source"
    elif total > SOURCE_BYTE_LIMIT:
        record["outcome"]["status"] = "editor_evidence_limit"
    elif contents:
        _edit_source(contents, issue=public["problem_statement"], aider=aider, model=model,
                     ollama_url=ollama_url, workspace=destination, record=record, windows=windows)
    return record, save_episode_prediction(destination, record, model=model)
