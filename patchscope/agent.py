"""Single v0.2 investigation-and-repair episode.

The original v0.1 workflow remains available as scripts/compare_conditions.py.
Only one explicit source replacement can be proposed and verified per run.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from time import perf_counter

from patchscope.experiment import run_id
from patchscope.interventions import build_intervention
from patchscope.protocol import (
    TOOLS, TOOLS_NAVIGATION, TOOL_MODE_NATIVE_REQUIRED, RangedReadProtocolError, ToolProtocolError, assistant_message, decode_message,
)
from patchscope.repair import (
    apply_exact_edit, apply_line_edit, render_repair_diff, run_pytest, temporary_repo,
)
from patchscope.proposal_contract import (
    LEGACY_CONTRACT, LINE_CONTRACT, normalize_newlines, observed_span, render_observed_spans,
)
from patchscope.proposal_source import (
    SOURCE_BYTE_LIMIT, describe_proposal_sources, read_proposal_sources,
)
from patchscope.proposal_windows import describe_replayed_spans
from patchscope.tools import is_test_path, list_source_files, read_source_file
from patchscope.navigation import read_file_range, search_code
from patchscope.source_map import source_reference_map
from patchscope.operative_trace import trace_public_reproducer, render_trace_hint
from patchscope.proposal_stage import ProposalProgress, propose_edit

SYSTEM_PROMPT = (
    "You are investigating a Python repository bug. Use native repository "
    "tools to inspect code; never invent the contents of a file. "
    "Stop exploring when enough relevant source evidence has been observed. "
    "Do not edit files or tests; a separate proposer will suggest a patch."
)


def _tool_result(repo: Path, action, observed: dict, seen_ranges=None,
                 observed_spans=None, *, file_inventory_limit=None,
                 exclude_tests=False) -> tuple[dict, bool, bool]:
    try:
        if action.name == "list_files":
            files = list_source_files(repo)
            if exclude_tests:
                files = [path for path in files if not is_test_path(path)]
            if file_inventory_limit is not None and len(files) > file_inventory_limit:
                return {"files": files[:file_inventory_limit], "total_files": len(files),
                        "truncated": True,
                        "hint": "Use search_code to find implementation outside this preview"}, False, True
            return {"files": files}, False, True
        if action.name == "search_code":
            return search_code(repo, action.arguments["query"]), False, True
        if action.name == "read_file_range":
            args = action.arguments
            key = (args["path"], args["start_line"], args["end_line"])
            if seen_ranges is not None and key in seen_ranges:
                return {"path": args["path"], "already_provided": True,
                        "hint": "Try a different line range or search_code"}, True, True
            result = read_file_range(repo, *key)
            if seen_ranges is not None:
                seen_ranges.add(key)
            fragment = result["content"]
            if observed_spans is not None:
                observed_spans.append(observed_span(
                    args["path"], result["start_line"], fragment))
            previous = observed.get(args["path"], "")
            if fragment not in previous:
                # Separate non-contiguous observations to avoid silently
                # presenting them as adjacent source lines.
                observed[args["path"]] = (previous + "\n\n# PATCHSCOPE_OBSERVED_RANGE_BOUNDARY\n"
                                          + fragment) if previous else fragment
            return result, False, True
        path = action.arguments["path"]
        if exclude_tests and is_test_path(path):
            raise ValueError("Test source is not readable by navigation")
        # Seed excerpts can be shorter than the normal tool-read limit.
        # A request for a partly seeded file must actually reveal its additional
        # contents rather than being dismissed as an unhelpful duplicate read.
        result = read_source_file(repo, path, max_chars=2000)
        if exclude_tests and is_test_path(result["path"]):
            raise ValueError("Test source is not readable by navigation")
        previous = observed.get(path)
        if previous is not None and len(previous) >= len(result["content"]):
            return {"path": path, "already_provided": True,
                    "hint": "Use search_code or read_file_range instead of rereading the prefix"}, True, True
        expanded = previous is not None
        observed[path] = result["content"]
        if observed_spans is not None:
            observed_spans.append(observed_span(path, 1, result["content"]))
        if expanded:
            result["expanded_from_seed"] = True
        return result, False, True
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}, False, False


def run_episode(
    *, item: dict, manifest: dict, root: Path, client, model: str,
    provenance: dict, allow_trusted_execution: bool = False,
    tool_mode: str = TOOL_MODE_NATIVE_REQUIRED, replay_spans: list[dict] | None = None,
) -> dict:
    """Run one episode using an injected OpenAI-compatible client.

    Offline testing can inject a scripted client. Never runs tests on original
    repositories. Test execution requires an explicit opt-in AND a trusted task.
    A temporary folder is NOT a security sandbox for generated Python code.
    """
    start = perf_counter()
    task, condition = item["task"], item["condition"]
    budgets = manifest["budgets"]
    proposal_reasoning_effort = manifest["model"].get("proposal_reasoning_effort")
    behavioral_proposal = manifest["model"].get("behavioral_proposal", False)
    repo = (root / task["repo_path"]).resolve()
    issue = (root / task["issue_path"]).read_text(encoding="utf-8")
    seed = build_intervention(
        condition, repo_path=repo, issue_text=issue,
        oracle_paths=task["oracle"]["paths"], placebo_pool=task["placebo_pool"],
        misleading_pool=task.get("misleading_pool", []),
        rng=random.Random(item["block_seed"]), top_k=manifest["retrieval"]["top_k"],
        char_budget=budgets["seed_char_budget"],
    )
    observed = {
        entry["path"]: read_source_file(repo, entry["path"], max_chars=2000)["content"]
        for entry in seed["sources"]
    }
    # `observed` must never contain more than the evidence actually displayed.
    # With default 1600-char code cap, all files in these fixtures fit.
    for entry in seed["sources"]:
        path = entry["path"]
        full = observed[path]
        actual_seed_code_len = entry["chars"]
        observed[path] = full[:actual_seed_code_len]

    # Public reproduction evidence is supplied BEFORE tool exploration so the
    # agent can inspect a previously unseen operative module. At proposal time,
    # an exact-edit contract restricts patches to source already observed.
    # Showing paths only after exploration could make a remedy impossible.
    operative_policy = manifest.get("operative_trace_policy", "off")
    operative_trace = None
    trace_hint = ""
    trace_init_error = None
    if operative_policy == "public_reproducer":
        try:
            if not (allow_trusted_execution and task["trusted_execution"]):
                raise ValueError("public_reproducer_requires_trusted_execution_opt_in")
            script = (root / task["public_reproducer_path"]).resolve()
            operative_trace = trace_public_reproducer(
                repo, script, timeout=min(task["verification"]["timeout_seconds"], 30))
            trace_hint = render_trace_hint(operative_trace)
        except (ValueError, OSError, TimeoutError) as exc:
            trace_init_error = exc
    prompt = f"Bug report:\n{issue}\n\nLocate the faulty implementation using repository tools."
    if seed["seed_text"]:
        prompt += "\n\nInitial repository evidence (may be irrelevant):\n" + seed["seed_text"]
    if trace_hint:
        prompt += "\n\n" + trace_hint
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    transcript = list(messages)
    trajectory = []
    usage_events = []
    error = None
    status = "incomplete"
    model_calls = 0
    tool_calls = 0
    invalid_calls = 0
    repeated_reads = 0
    agent_final = None
    proposal_progress = ProposalProgress()
    proposal_diff = None
    verification = {"baseline_passed": None, "patched_passed": None}
    modes_observed = set()
    # New navigation tools are explicit opt-in; old research manifests behave
    # identically, including their original prompts and source-read policies.
    navigation_enabled = manifest.get("repo_tools_policy", "basic") == "navigation_v1"
    enabled_tools = TOOLS_NAVIGATION if navigation_enabled else TOOLS
    allowed_tool_names = {t["function"]["name"] for t in enabled_tools}
    tool_call_recovery = navigation_enabled and manifest.get("tool_call_recovery", False)
    rejected_range_read = None
    range_read_recovered = False
    seen_ranges = set()
    if navigation_enabled:
        messages[0]["content"] += (
            " For large files, read_file returns only an initial prefix. "
            "Never repeat the same read_file(path). Use search_code for symbols "
            "and read_file_range(path, start_line, end_line) around traceback "
            "locations. Stop exploring when you have enough code to repair."
        )
        transcript[0] = dict(messages[0])
    evidence_policy = manifest.get("evidence_policy", "off")
    proposal_evidence = None
    proposal_source = None
    matched_source = manifest.get("matched_source", False)
    proposal_contract = manifest.get("proposal_contract", LEGACY_CONTRACT)
    if proposal_contract not in {LEGACY_CONTRACT, LINE_CONTRACT}:
        raise ValueError("unknown_proposal_contract")
    observed_spans = [observed_span(path, 1, content)
                      for path, content in observed.items() if content]

    def event(kind, **fields):
        trajectory.append({"event_index": len(trajectory), "kind": kind, **fields})

    def ask(conversation, *, purpose, tools=None):
        nonlocal model_calls
        if model_calls >= budgets["max_model_calls"]:
            raise ValueError("model_call_budget_exhausted")
        total = sum(u["prompt_tokens"] + u["completion_tokens"] for u in usage_events)
        if total >= budgets["soft_total_token_budget"]:
            raise ValueError("soft_token_budget_exhausted")
        # A distinct proposal ceiling is an explicit protocol intervention.
        # Never silently change the v0.2/v0.2.3 manifests, which still use the
        # common ceiling for both exploration and patch generation.
        is_proposal = purpose in {"patch_proposal", "patch_contract_retry"}
        completion_cap = (budgets.get("max_patch_completion_tokens_per_call",
                                      budgets["max_completion_tokens_per_call"])
                          if is_proposal
                          else budgets["max_completion_tokens_per_call"])
        kwargs = {
            "model": model, "messages": copy.deepcopy(conversation),
            "seed": item["model_seed"],
            "temperature": manifest["model"].get("temperature", 0),
            "max_tokens": completion_cap,
        }
        if tools is not None:
            kwargs.update(tools=tools, tool_choice="auto")
        if is_proposal and proposal_reasoning_effort is not None:
            kwargs["extra_body"] = {"reasoning_effort": proposal_reasoning_effort}
        response = client.chat.completions.create(**kwargs)
        model_calls += 1
        stats = response.usage
        if stats is None or stats.prompt_tokens is None or stats.completion_tokens is None:
            raise ValueError("model_usage_missing")
        choice = response.choices[0]
        message = choice.message
        row = {"purpose": purpose, "prompt_tokens": stats.prompt_tokens,
               "completion_tokens": stats.completion_tokens,
               "requested_max_tokens": completion_cap,
               "finish_reason": getattr(choice, "finish_reason", None),
               "visible_response_chars": len(getattr(message, "content", None) or ""),
               "reasoning_output_present": bool(getattr(message, "reasoning", None)
                                                or getattr(message, "reasoning_content", None))}
        usage_events.append(row)
        event("model_response", model_call=model_calls, **row)
        return message

    try:
        if trace_init_error is not None:
            raise trace_init_error
        if operative_trace is not None:
            event("public_reproducer_trace", paths=operative_trace["executed_paths"],
                  script_sha256=operative_trace["public_reproducer_sha256"],
                  elapsed_ms=operative_trace["elapsed_ms"])
        max_steps = budgets["max_steps"] if replay_spans is None else 0
        for step in range(1, max_steps + 1):
            assistant = ask(messages, purpose="exploration", tools=enabled_tools)
            raw_assistant = assistant_message(assistant)
            messages.append(raw_assistant)
            transcript.append(raw_assistant)
            try:
                actions, agent_final = decode_message(
                    assistant, mode=tool_mode, allowed_tools=allowed_tool_names,
                    recover_ranged_read=(
                        tool_call_recovery and rejected_range_read is None
                        and step < budgets["max_steps"]
                        and tool_calls + 1 < budgets["max_tool_calls"]
                        and model_calls < budgets["max_model_calls"]
                    ),
                )
            except RangedReadProtocolError as exc:
                invalid_calls += 1
                tool_calls += 1
                modes_observed.add("native")
                rejected_range_read = (step, exc.path)
                actions, agent_final = [], None
                event("protocol_error", step=step, message=str(exc))
                reply = {
                    "role": "tool",
                    "tool_call_id": exc.call_id,
                    "content": json.dumps({
                        "error": "range_arguments_on_read_file",
                        "hint": "Use read_file_range with path, start_line and end_line. "
                                "Send line numbers as JSON integers and request 1-60 lines.",
                    }),
                }
                messages.append(reply)
                transcript.append(reply)
                event("ranged_read_feedback", step=step)
            except ToolProtocolError as exc:
                invalid_calls += 1
                event("protocol_error", step=step, message=str(exc))
                raise
            if not actions and not (rejected_range_read and rejected_range_read[0] == step):
                status = "exploration_finished"
                break
            for action in actions:
                if tool_calls >= budgets["max_tool_calls"]:
                    raise ValueError("tool_call_budget_exhausted")
                tool_calls += 1
                modes_observed.add(action.mode)
                result, repeated, valid = _tool_result(
                    repo, action, observed, seen_ranges if navigation_enabled else None,
                    observed_spans, file_inventory_limit=budgets.get("file_inventory_limit"),
                    exclude_tests=navigation_enabled)
                if repeated:
                    repeated_reads += 1
                if not valid:
                    invalid_calls += 1
                event("tool_call", step=step, name=action.name,
                      arguments=action.arguments, mode=action.mode,
                      repeated_read=repeated, valid=valid,
                      expanded_from_seed=bool(result.get("expanded_from_seed")))
                event("tool_result", step=step, name=action.name, result=result)
                if (valid and not repeated and not range_read_recovered
                        and action.name == "read_file_range"
                        and rejected_range_read == (step - 1, action.arguments["path"])):
                    event("ranged_read_recovered", step=step)
                    range_read_recovered = True
                if action.call_id:
                    reply = {"role": "tool", "tool_call_id": action.call_id,
                             "content": json.dumps(result)}
                else:
                    reply = {"role": "user", "content": "Tool result:\n" + json.dumps(result)}
                messages.append(reply)
                transcript.append(reply)
            if navigation_enabled:
                # Stop exploration early enough to reserve a model request for
                # patch generation. This is a soft reservation, not a hard cap.
                used = sum(u["prompt_tokens"] + u["completion_tokens"]
                           for u in usage_events)
                reserve = budgets.get("proposal_reserve_tokens", 0)
                if reserve and used >= budgets["soft_total_token_budget"] - reserve:
                    event("exploration_stopped_for_proposal_budget", used_tokens=used,
                          reserved_tokens=reserve)
                    status = "exploration_budget_reserved"
                    break
        else:
            status = "exploration_step_limit"

        if replay_spans is not None:
            observed_spans = replay_spans
            observed = {span["path"]: span["content"] for span in replay_spans}
            if replay_spans:
                proposal_source = describe_replayed_spans(replay_spans)
                event("matched_proposal_source", sha256=proposal_source["sha256"])
        if not observed:
            raise ValueError("no_source_code_observed")
        if matched_source and replay_spans is None:
            contents, total = read_proposal_sources(repo, sorted(observed))
            if total > SOURCE_BYTE_LIMIT:
                raise ValueError("proposal_source_byte_limit")
            observed_spans = [
                observed_span(path, 1, normalize_newlines(content.decode("utf-8")))
                for path, content in contents.items() if content
            ]
            proposal_source = describe_proposal_sources(contents)
            event("matched_proposal_source", sha256=proposal_source["sha256"], source_bytes=total)
        observed_text = (render_observed_spans(observed_spans)
                         if proposal_contract == LINE_CONTRACT else
                         "\n\n".join(f"FILE: {path}\n{code}"
                                     for path, code in observed.items()))
        proposal_evidence = source_reference_map(
            repo, policy=evidence_policy,
            max_chars=budgets.get("source_map_char_budget", 1400),
        )
        event("proposal_evidence", policy=evidence_policy,
              chars=proposal_evidence["chars"], sha256=proposal_evidence["sha256"],
              static_edges=proposal_evidence["static_edges"],
              truncated=proposal_evidence["truncated"])
        # Source-inventory/import evidence from v0.5 remains proposal-only.
        # Runtime evidence is now seen during exploration and therefore does
        # not need to be duplicated in the proposal prompt.
        extra = ("\n\n" + proposal_evidence["text"]
                 if proposal_evidence["text"] else "")
        original, changed = propose_edit(
            repo=repo, issue=issue, observed_text=observed_text, extra=extra,
            observed=observed, observed_spans=observed_spans, proposal_contract=proposal_contract,
            behavioral_proposal=behavioral_proposal, max_patch_retries=budgets.get("max_patch_retries", 0),
            transcript=transcript, usage_events=usage_events, progress=proposal_progress,
            ask=ask, event=event,
        )
        proposal = proposal_progress.proposal
        event("patch_proposal", path=proposal["path"], contract=proposal_contract)
        proposal_diff = render_repair_diff(proposal["path"], original, changed)
        if not task["trusted_execution"] or not allow_trusted_execution:
            status = "proposal_requires_explicit_verification_opt_in"
        else:
            with temporary_repo(repo) as working:
                baseline = run_pytest(working, timeout=task["verification"]["timeout_seconds"])
                verification["baseline_passed"] = baseline["passed"]
                event("test_execution", phase="baseline", passed=baseline["passed"], exit_code=baseline["exit_code"])
                if baseline["passed"]:
                    status = "baseline_already_passes"
                else:
                    if proposal_contract == LINE_CONTRACT:
                        apply_line_edit(working, proposal)
                    else:
                        apply_exact_edit(working, proposal["path"], proposal["old"], proposal["new"])
                    event("patch_application", path=proposal["path"], applied=True)
                    patched = run_pytest(working, timeout=task["verification"]["timeout_seconds"])
                    verification["patched_passed"] = patched["passed"]
                    event("test_execution", phase="patched", passed=patched["passed"], exit_code=patched["exit_code"])
                    status = "resolved" if patched["passed"] else "repair_failed_tests"
    except (ToolProtocolError, ValueError, OSError, TimeoutError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        status = ("protocol_error" if isinstance(exc, ToolProtocolError)
                  else "budget_exhausted" if navigation_enabled and
                  "budget_exhausted" in str(exc) else "error")
    except Exception as exc:
        # Preserve a durable failed run record; never conceal or mark it successful.
        error = f"{type(exc).__name__}: {exc}"
        status = "error"

    prompt_tokens = sum(e["prompt_tokens"] for e in usage_events)
    completion_tokens = sum(e["completion_tokens"] for e in usage_events)
    generation = {"model": model, "temperature": manifest["model"].get("temperature", 0),
                  "seed": item["model_seed"], "tool_policy": tool_mode}
    if proposal_reasoning_effort is not None:
        generation["proposal_reasoning_effort"] = proposal_reasoning_effort
    if behavioral_proposal:
        generation["behavioral_proposal"] = True
    return {
        "schema_version": 2,
        "experiment_id": manifest["experiment_id"],
        "run_id": run_id(item),
        "task_id": item["task_id"], "condition": condition,
        "repetition": item["repetition"],
        "provenance": {**provenance, "generation": generation},
        "budgets": dict(budgets),
        "intervention": {k: v for k, v in seed.items() if k != "seed_text"},
        "transcript": transcript, "trajectory": trajectory,
        "usage": {
            "model_calls": model_calls, "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens,
            "tool_calls": tool_calls, "invalid_tool_calls": invalid_calls,
            "repeated_reads": repeated_reads, "retrieval_ms": seed["retrieval_ms"],
            "wall_seconds": round(perf_counter() - start, 3),
            "soft_budget_overshoot": max(0, prompt_tokens + completion_tokens - budgets["soft_total_token_budget"]),
            "usage_events": usage_events,
            "tool_protocols_observed": sorted(modes_observed),
        },
        "observed_paths": sorted(observed), "agent_final": agent_final,
        "proposal": proposal_progress.proposal, "proposal_diff": proposal_diff,
        "static_review": proposal_progress.static_review,
        "proposal_attempts": proposal_progress.attempts,
        "proposal_evidence": (
            {k: v for k, v in proposal_evidence.items() if k != "text"}
            if proposal_evidence is not None else {"policy": evidence_policy}
        ),
        "operative_trace_policy": manifest.get("operative_trace_policy", "off"),
        "operative_trace": operative_trace,
        "proposal_protocol": {"contract": proposal_contract,
                              "max_patch_retries": budgets.get("max_patch_retries", 0),
                              "attempted": len(proposal_progress.attempts)},
        **({"tool_call_recovery": True} if tool_call_recovery else {}),
        **({"matched_source": True, "proposal_source": proposal_source} if matched_source else {}),
        **({"proposal_windows": replay_spans} if replay_spans is not None else {}),
        "verification": verification,
        "outcome": {"status": status, "repair_verified": status == "resolved"},
        "error": error,
    }
