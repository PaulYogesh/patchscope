"""Controlled proposal-only replay from a native PatchScope exploration record.

This is a new experimental protocol: no exploration model calls, no model-visible
oracle labels, and no claim that a static import proves runtime reachability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

from patchscope.proposal_stage import EXACT_FRAGMENT_FEEDBACK, PATCH_PROMPT
from patchscope.proposal_contract import ProposalContractError, inspect_proposal_text, validate_proposal
from patchscope.protocol import parse_json_dict
from patchscope.repair import apply_exact_edit, render_repair_diff, run_pytest, temporary_repo
from patchscope.source_map import POLICIES, source_reference_map
from patchscope.tools import read_source_file


REPLAY_ID = "frozen-proposal-v051"
SOURCE_ID = "interference-smoke-v030"
SOURCE_MANIFEST = "experiments/interference_smoke_v030.json"


def sha256_blob(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def frozen_observations(record: dict, *, repo: Path, issue: str) -> dict[str, str]:
    """Rebuild exact displayed read_file contents; reject stale/incomplete snapshots.

    The source experiment is native with no initial seeded source. The model's
    observed dictionary is populated by the content in tool_result events.
    Re-read only to verify bytes, NOT to add extra unseen information.
    """
    if record.get("condition") != "native":
        raise ValueError("frozen_replay_requires_native_source")
    if (record.get("intervention") or {}).get("sources"):
        raise ValueError("seeded_source_not_supported_by_replay")
    prompts = [x.get("content", "") for x in record.get("transcript", [])
               if x.get("role") == "user" and isinstance(x.get("content"), str)]
    if not prompts or not prompts[0].startswith(f"Bug report:\n{issue}\n\n"):
        raise ValueError("source_issue_mismatch")
    observed: dict[str, str] = {}
    for event in record.get("trajectory", []):
        if event.get("kind") != "tool_result" or event.get("name") != "read_file":
            continue
        result = event.get("result") or {}
        path, content = result.get("path"), result.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            continue  # repeated reads or invalid tool calls do not add evidence
        actual = read_source_file(repo, path, max_chars=2000)["content"]
        if content != actual:
            raise ValueError(f"frozen_source_content_mismatch:{path}")
        observed[path] = content
    if not observed or sorted(observed) != sorted(record.get("observed_paths", [])):
        raise ValueError("frozen_observed_paths_mismatch")
    return observed


def prepare_frozen(root: Path, source_record: dict, task: dict, *, source_id: str = SOURCE_ID) -> dict:
    repo = (root / task["repo_path"]).resolve()
    issue = (root / task["issue_path"]).read_text(encoding="utf-8")
    if source_record.get("experiment_id") != source_id or source_record.get("task_id") != task["task_id"]:
        raise ValueError("source_record_task_or_experiment_mismatch")
    if source_record.get("outcome", {}).get("status") in {None, "incomplete"}:
        raise ValueError("source_episode_incomplete")
    observed = frozen_observations(source_record, repo=repo, issue=issue)
    text = "\n\n".join(f"FILE: {path}\n{code}" for path, code in observed.items())
    return {
        "repo": repo, "issue": issue, "observed": observed,
        "observed_text": text,
        "snapshot_sha256": sha256_blob(json.dumps(observed, ensure_ascii=False, separators=(",", ":")).encode()),
    }


def propose_frozen(*, client, model: str, policy: str, task: dict, source_record: dict,
                   source_manifest: dict, root: Path, provenance: dict,
                   allow_trusted_execution: bool = False) -> dict:
    """A fresh proposal on a frozen historical source snapshot, then optional pytest.

    Does not generate, modify, or read any new exploration evidence. All model
    calls consume the same observed_text; only the proposal-stage hint differs.
    """
    if policy not in POLICIES:
        raise ValueError("invalid_replay_policy")
    start = perf_counter()
    prepared = prepare_frozen(root, source_record, task,
                              source_id=source_manifest["experiment_id"])
    repo, issue, observed = (prepared[k] for k in ("repo", "issue", "observed"))
    budgets = source_manifest["budgets"]
    hint = source_reference_map(repo, policy=policy,
                                max_chars=budgets.get("source_map_char_budget", 1400))
    extra = "\n\n" + hint["text"] if hint["text"] else ""
    messages = [
        {"role": "system", "content": PATCH_PROMPT},
        {"role": "user", "content": (
            f"Bug report:\n{issue}\n\nObserved source:\n{prepared['observed_text']}"
            f"{extra}\n\nPropose the smallest justified repair.")},
    ]
    attempts = []
    usage_events = []
    proposal = None
    status = "incomplete"
    error = None
    verification = {"baseline_passed": None, "patched_passed": None}
    diff = None
    transcript = list(messages)
    patch_limit = budgets.get("max_patch_completion_tokens_per_call",
                              budgets["max_completion_tokens_per_call"])
    retries = budgets.get("max_patch_retries", 0)
    try:
        for attempt in range(retries + 1):
            purpose = "patch_proposal" if attempt == 0 else "patch_contract_retry"
            response = client.chat.completions.create(
                model=model, messages=json.loads(json.dumps(messages)),
                seed=source_record["provenance"]["generation"]["seed"],
                temperature=source_manifest["model"].get("temperature", 0),
                max_tokens=patch_limit,
            )
            choice = response.choices[0]
            content = getattr(choice.message, "content", None)
            tokens = response.usage
            if (tokens is None or tokens.prompt_tokens is None
                    or tokens.completion_tokens is None):
                raise ValueError("model_usage_missing")
            stats = {"purpose": purpose, "prompt_tokens": tokens.prompt_tokens,
                     "completion_tokens": tokens.completion_tokens,
                     "requested_max_tokens": patch_limit,
                     "finish_reason": getattr(choice, "finish_reason", None)}
            usage_events.append(stats)
            messages.append({"role": "assistant", "content": content})
            transcript.append({"role": "assistant", "purpose": purpose, "content": content})
            structure = inspect_proposal_text(content)
            diagnostic = {
                "attempt": attempt + 1,
                "structure": structure,
                "finish_reason": stats["finish_reason"],
                "completion_tokens": stats["completion_tokens"],
                "requested_max_tokens": patch_limit,
                "at_completion_cap": stats["completion_tokens"] >= patch_limit,
                "response_chars": structure["response_chars"],
            }
            try:
                proposal = validate_proposal(parse_json_dict(content), observed, repo)
            except ProposalContractError as exc:
                attempts.append({**diagnostic, "valid": False, "reason": exc.code})
                if attempt == retries:
                    raise
                feedback = {
                    "role": "user",
                    "content": f"Your proposed JSON edit was rejected ({exc.code}). " + EXACT_FRAGMENT_FEEDBACK,
                }
                messages.append(feedback)
                transcript.append({"purpose": "patch_contract_feedback", **feedback})
            else:
                attempts.append({**diagnostic, "valid": True, "reason": None})
                break
        if not task.get("trusted_execution") or not allow_trusted_execution:
            status = "proposal_requires_explicit_verification_opt_in"
        else:
            with temporary_repo(repo) as copy_repo:
                baseline = run_pytest(copy_repo, timeout=task["verification"]["timeout_seconds"])
                verification["baseline_passed"] = baseline["passed"]
                if baseline["passed"]:
                    status = "baseline_already_passes"
                else:
                    apply_exact_edit(copy_repo, proposal["path"], proposal["old"], proposal["new"])
                    patched = run_pytest(copy_repo, timeout=task["verification"]["timeout_seconds"])
                    verification["patched_passed"] = patched["passed"]
                    verification["patched_exit_code"] = patched["exit_code"]
                    verification["patched_output_tail"] = patched["output"]
                    status = "resolved" if patched["passed"] else "repair_failed_tests"
    except (ValueError, OSError, TimeoutError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        status = "error"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        status = "error"
    if proposal is not None:
        original = (repo / proposal["path"]).read_text(encoding="utf-8")
        changed = original.replace(proposal["old"], proposal["new"], 1)
        diff = render_repair_diff(proposal["path"], original, changed)
    prompt_tokens = sum(x["prompt_tokens"] for x in usage_events)
    completion_tokens = sum(x["completion_tokens"] for x in usage_events)
    return {
        "schema_version": 3, "experiment_id": REPLAY_ID,
        "task_id": task["task_id"], "policy": policy,
        "repetition": source_record["repetition"], "condition": "native",
        "run_id": f"{task['task_id']}__{policy}__r{source_record['repetition']:02d}",
        "source": {"experiment_id": source_record["experiment_id"],
                   "run_id": source_record["run_id"],
                   "observed_paths": list(observed),
                   "snapshot_sha256": prepared["snapshot_sha256"],
                   "source_proposal_path": (source_record.get("proposal") or {}).get("path"),
                   "source_verified": source_record["outcome"].get("repair_verified"),
                   "source_model_digest": source_record["provenance"].get("ollama", {}).get("digest")},
        "provenance": {**provenance, "generation": {
            "model": model, "seed": source_record["provenance"]["generation"]["seed"],
            "temperature": source_manifest["model"].get("temperature", 0),
            "protocol": "frozen-exploration-proposal-only-v051"}},
        "budgets": {"patch_completion_limit": patch_limit, "max_patch_retries": retries},
        "proposal_evidence": {k: v for k, v in hint.items() if k != "text"},
        "proposal": proposal, "proposal_diff": diff, "proposal_attempts": attempts,
        "transcript": transcript, "verification": verification,
        "usage": {"model_calls": len(usage_events), "prompt_tokens": prompt_tokens,
                  "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens,
                  "usage_events": usage_events, "wall_seconds": round(perf_counter()-start, 3)},
        "outcome": {"status": status, "repair_verified": status == "resolved"},
        "error": error,
    }


def compare_frozen(records: dict[str, dict[tuple[str, int], dict]]) -> dict:
    """Strictly compare replayed policies on identical frozen observation hashes."""
    if set(records) != set(POLICIES):
        raise ValueError("replay_requires_three_policies")
    keys = {p: set(rows) for p, rows in records.items()}
    if not all(keys.values()) or len(set(map(frozenset, keys.values()))) != 1:
        raise ValueError("incomplete_or_unmatched_frozen_replays")
    results = []
    for task_id, repetition in sorted(next(iter(keys.values()))):
        group = {p: records[p][(task_id, repetition)] for p in POLICIES}
        if any(r.get("policy") != p for p, r in group.items()):
            raise ValueError(f"frozen_replay_policy_mismatch:{task_id}")
        if any(r.get("task_id") != task_id or r.get("repetition") != repetition for r in group.values()):
            raise ValueError(f"frozen_replay_key_mismatch:{task_id}")
        hashes = {r["source"]["snapshot_sha256"] for r in group.values()}
        sources = {r["source"]["run_id"] for r in group.values()}
        source_paths = {tuple(r["source"]["observed_paths"]) for r in group.values()}
        digests = {r["provenance"].get("ollama", {}).get("digest") for r in group.values()}
        seeds = {r["provenance"]["generation"]["seed"] for r in group.values()}
        model_names = {r["provenance"]["generation"]["model"] for r in group.values()}
        budgets = {json.dumps(r["budgets"], sort_keys=True) for r in group.values()}
        if any(len(x) != 1 for x in (hashes, sources, source_paths, digests, seeds, model_names, budgets)):
            raise ValueError(f"frozen_replay_provenance_mismatch:{task_id}")
        if any(r["source"].get("source_model_digest") != r["provenance"].get("ollama",{}).get("digest")
               for r in group.values()):
            raise ValueError(f"frozen_replay_source_model_mismatch:{task_id}")
        if next(iter(digests)) in {None, "unavailable"}:
            raise ValueError(f"frozen_replay_digest_unavailable:{task_id}")
        results.append({
            "task_id": task_id,
            "source_snapshot_sha256": next(iter(hashes)),
            "paths_observed": group["off"]["source"]["observed_paths"],
            "static_import_edges": group["imports"]["proposal_evidence"]["static_edges"],
            "verified": {p: bool(group[p]["outcome"]["repair_verified"]) for p in POLICIES},
            "status": {p: group[p]["outcome"]["status"] for p in POLICIES},
            "patch": {p: (group[p].get("proposal") or {}).get("path") for p in POLICIES},
            "proposal_tokens": {p: group[p]["usage"]["total_tokens"] for p in POLICIES},
        })
    return {"n_tasks": len({r["task_id"] for r in results}),
            "n_matched": len(results), "results": results}


def render_frozen(report: dict) -> str:
    lines = ["# PatchScope v0.5.1 — frozen-exploration proposal comparison", "",
             f"Compared {report['n_matched']} matched task episodes; no exploration rerun.",
             "All three policies receive exactly the same recorded source excerpts. "
             "Only proposal-stage evidence hints differ.", "",
             "| Task | Static edges | Off | Inventory | Imports | Patch path (off / inventory / imports) |",
             "|---|---:|---|---|---|---|",]
    for row in report["results"]:
        cells = [f"`{row['task_id']}`", str(row["static_import_edges"])]
        cells += ["verified" if row["verified"][p] else row["status"][p] for p in POLICIES]
        cells += [" / ".join(f"`{row['patch'][p]}`" for p in POLICIES)]
        lines.append("| " + " | ".join(cells) + " |")
    for p in POLICIES:
        n = sum(row["verified"][p] for row in report["results"])
        lines.append(f"- **{p}:** {n}/{report['n_matched']} verified")
    lines.extend(["", "## Interpretation limits", "",
        "This is a **proposal-stage** comparison on previously selected source excerpts, "
        "not a whole-agent repair evaluation. All frozen excerpts, seeds and model digests "
        "are checked for equality across arms. Prompt sizes and wording differ. "
        "Randomness can remain despite fixed seeds.", "",
        "The original four tasks contain no explicit static source-import edges; "
        "this treatment should not be described as a dependency-aware solution "
        "if the report confirms zero edges. No gold-path labels are passed to the model.", ""])
    return "\n".join(lines)
