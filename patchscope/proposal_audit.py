"""Offline response-format audit for original and new run JSON records.

No model calls, patch execution, or transcript/source-text export. Inspect one
representative per task-condition, since deterministic repeats may be identical.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from patchscope.proposal_contract import inspect_proposal_text


def audit_proposals(records: list[dict]) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    counters = Counter()
    for r in records:
        groups[(r["task_id"], r["condition"])].append(r)
        counters[r["outcome"]["status"]] += 1
    examples = []
    for (task, condition), rows in sorted(groups.items()):
        exemplar = sorted(rows, key=lambda r: r["repetition"])[0]
        proposals = [e for e in exemplar.get("transcript", []) if
                     e.get("role") == "assistant" and e.get("purpose") in
                     {"patch_proposal", "patch_contract_retry"}]
        first = proposals[0] if proposals else {}
        inspection = inspect_proposal_text(first.get("content")) if proposals else {
            "code": "proposal_response_not_found", "response_chars": 0,
            "fields": [], "valid_json_object": False,
        }
        usage = [e for e in exemplar.get("usage", {}).get("usage_events", [])
                 if e.get("purpose") in {"patch_proposal", "patch_contract_retry"}]
        attempt_logs = exemplar.get("proposal_attempts", [])
        first_usage = usage[0] if usage else {}
        first_cap = first_usage.get(
            "requested_max_tokens", exemplar.get("budgets", {}).get(
                "max_patch_completion_tokens_per_call",
                exemplar.get("budgets", {}).get("max_completion_tokens_per_call")))
        first_tokens = first_usage.get("completion_tokens")
        examples.append({
            "task": task, "condition": condition, "runs_in_group": len(rows),
            "status": exemplar["outcome"]["status"],
            "original_response": inspection,
            "proposal_completion_tokens": first_tokens,
            "per_call_completion_ceiling": first_cap,
            "finish_reason": first_usage.get("finish_reason"),
            "at_completion_ceiling": (first_tokens >= first_cap)
                                     if isinstance(first_tokens, int) and isinstance(first_cap, int)
                                     else None,
            "attempt_count": len(attempt_logs) if attempt_logs else len(usage),
            "proposal_rejections": [e.get("reason") for e in attempt_logs if not e.get("valid")],
        })
    return {"total_runs": len(records), "outcome_counts": dict(sorted(counters.items())),
            "groups": examples}


def render_proposal_audit(report: dict) -> str:
    lines = ["# PatchScope — offline proposal-response audit", "",
             "Examines the saved *original* proposal response. No LLM calls, "
             "source-code execution, or raw source/prompt export.", "",
             "| Task | Condition | Result | Proposal format | Response chars | Completion tokens / call limit | Cap hit | Finish reason | Attempts | Rejections |",
             "|---|---|---|---|---:|---:|---|---|---:|---|"]
    for row in report["groups"]:
        i = row["original_response"]
        tokens = row["proposal_completion_tokens"]
        ceiling = row["per_call_completion_ceiling"]
        token_label = f"{tokens if tokens is not None else '—'} / {ceiling if ceiling is not None else '—'}"
        at_cap = row["at_completion_ceiling"]
        cap_label = "yes" if at_cap is True else ("no" if at_cap is False else "—")
        finish = row["finish_reason"] or "—"
        rejections = ", ".join(f"`{x}`" for x in row["proposal_rejections"]) or "—"
        lines.append(f"| `{row['task']}` | {row['condition']} | {row['status']} | "
                     f"`{i['code']}` | {i['response_chars']} | {token_label} | "
                     f"{cap_label} | {finish} | {row['attempt_count']} | {rejections} |")
    lines += ["", "`structure_valid` means the response had a three-field JSON shape. "
              "It does **not** guarantee the edit matches an observed source file. "
              "The old v0.2 `invalid_patch_proposal` error could indicate any "
              "nonconforming response, including malformed JSON. "
              "Hitting the completion ceiling suggests possible truncation but does not prove it. "
              "Some legacy logs omit the proposal response; those are labeled "
              "`proposal_response_not_found`. This audit cannot infer hidden reasoning "
              "or patch correctness."]
    return "\n".join(lines) + "\n"
