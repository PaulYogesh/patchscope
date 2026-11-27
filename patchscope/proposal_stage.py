"""Repair proposal prompts, contract feedback and static review."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from patchscope.proposal_contract import (
    LINE_CONTRACT, ProposalContractError, inspect_line_proposal_text,
    inspect_proposal_text, materialize_line_edit, observed_span,
    render_observed_spans, validate_line_proposal, validate_proposal,
)
from patchscope.protocol import assistant_message, parse_json_dict
from patchscope.static_review import review_python_edit

PATCH_PROMPT = (
    "You are a Python repair assistant. Given ONLY observed repository code, "
    "propose one minimal code edit. Output ONLY a valid JSON object with exactly "
    "three string fields: path, old, new. NO markdown, no code fences, no prose. "
    "Copy the old string EXACTLY from one observed source file; it must occur "
    "once in that file. Do not edit tests."
)
LINE_PATCH_PROMPT = (
    "You are a Python repair assistant. Given ONLY line-numbered observed "
    "repository code, propose one minimal code edit. Output ONLY a valid JSON "
    "object with exactly four fields: path (string), start_line (integer), "
    "end_line (integer), replacement (string). The inclusive line range must "
    "be completely visible in the observed source. Replace the smallest "
    "justified range. Preserve required indentation and line endings in the "
    "replacement. Do not edit tests. No markdown, code fences, or prose."
)
EXACT_FRAGMENT_FEEDBACK = (
    "Respond with ONLY a JSON object with string fields path, old, "
    "new. Use an observed source file; copy an exact, uniquely "
    "occurring old fragment from the observed code. Do not include "
    "markdown or explanations. Do not edit tests."
)


@dataclass
class ProposalProgress:
    """Proposal data retained in the episode even when an attempt fails."""

    proposal: dict | None = None
    static_review: dict | None = None
    attempts: list[dict] = field(default_factory=list)


def propose_edit(
    *, repo: Path, issue: str, observed_text: str, extra: str, observed: dict,
    observed_spans: list[dict], proposal_contract: str, behavioral_proposal: bool,
    max_patch_retries: int, transcript: list[dict], usage_events: list[dict],
    progress: ProposalProgress, ask, event,
) -> tuple[str, str]:
    """Request and review an edit while preserving proposal diagnostics."""
    proposal_prompt = LINE_PATCH_PROMPT if proposal_contract == LINE_CONTRACT else PATCH_PROMPT
    if behavioral_proposal:
        proposal_prompt += (
            " Identify the reported incorrect behavior and the desired behavior from the bug "
            "report. Use the observed code to choose a minimal change that causes the desired "
            "behavior on the reported input and preserves unrelated behavior. Before responding, "
            "compare your replacement to the observed code and check that it changes the "
            "relevant behavior. Apply this check on retries as well. Keep the required output format."
        )
    proposal_messages = [
        {"role": "system", "content": proposal_prompt},
        {"role": "user", "content": f"Bug report:\n{issue}\n\nObserved source:\n{observed_text}{extra}\n\nPropose the smallest justified repair."},
    ]
    # Store repair conversation too; all model calls count toward cost.
    transcript.extend([{"purpose": "proposal", **m} for m in proposal_messages])
    for attempt in range(max_patch_retries + 1):
        progress.proposal = None
        progress.static_review = None
        purpose = "patch_proposal" if attempt == 0 else "patch_contract_retry"
        answer = ask(proposal_messages, purpose=purpose)
        reply = assistant_message(answer)
        transcript.append({"purpose": purpose, **reply})
        proposal_messages.append(reply)
        structure = (inspect_line_proposal_text(answer.content)
                     if proposal_contract == LINE_CONTRACT
                     else inspect_proposal_text(answer.content))
        completion = usage_events[-1]
        # An exhausted completion allocation can truncate generated JSON,
        # but matching the cap does NOT itself establish truncation.
        attempt_diagnostics = {
            "finish_reason": completion["finish_reason"],
            "completion_tokens": completion["completion_tokens"],
            "requested_max_tokens": completion["requested_max_tokens"],
            "at_completion_cap": (
                completion["completion_tokens"] >= completion["requested_max_tokens"]
            ),
            "finish_reason_length": completion["finish_reason"] == "length",
            "reasoning_output_present": completion["reasoning_output_present"],
            "response_chars": structure["response_chars"],
        }
        try:
            parsed = parse_json_dict(answer.content)
            proposal = (validate_line_proposal(parsed, observed_spans, repo)
                        if proposal_contract == LINE_CONTRACT
                        else validate_proposal(parsed, observed, repo))
            progress.proposal = proposal
        except ProposalContractError as exc:
            progress.attempts.append({
                "attempt": attempt + 1, "valid": False, "reason": exc.code,
                "structure": structure, **attempt_diagnostics,
            })
            event("patch_proposal_rejected", attempt=attempt + 1, reason=exc.code)
            if attempt == max_patch_retries:
                raise
            # Only correction of the output contract is requested. There is
            # no additional repository evidence or access to hidden labels.
            contract_instruction = (
                "Respond with ONLY a JSON object with fields path, start_line, "
                "end_line, replacement. Use a completely observed inclusive "
                "line range and preserve indentation. End a nonempty replacement "
                "with a newline if any original lines follow it. Do not include markdown "
                "or explanations. Do not edit tests."
                if proposal_contract == LINE_CONTRACT else EXACT_FRAGMENT_FEEDBACK
            )
            correction = {
                "role": "user",
                "content": (
                    f"Your proposed JSON edit was rejected ({exc.code}). "
                    + contract_instruction
                ),
            }
            proposal_messages.append(correction)
            transcript.append({"purpose": "patch_contract_feedback", **correction})
            event("patch_contract_retry_requested", attempt=attempt + 2, reason=exc.code)
            continue

        accepted = {
            "attempt": attempt + 1, "valid": True, "reason": None,
            "structure": structure, **attempt_diagnostics,
        }
        progress.attempts.append(accepted)
        target = repo / proposal["path"]
        if proposal_contract != LINE_CONTRACT:
            original = target.read_text(encoding="utf-8")
            changed = original.replace(proposal["old"], proposal["new"], 1)
            return original, changed

        original = target.read_bytes().decode("utf-8")
        old, changed = materialize_line_edit(proposal, original)
        static_review = review_python_edit(original, changed)
        progress.static_review = static_review
        accepted["static_review"] = static_review
        event("static_review", attempt=attempt + 1, **static_review)
        if static_review["passed"]:
            return original, changed
        code = static_review["code"]
        if code != "python_syntax_invalid" or attempt == max_patch_retries:
            raise ProposalContractError(code)

        original_range = render_observed_spans([
            observed_span(proposal["path"], proposal["start_line"], old),
        ])
        correction = {
            "role": "user",
            "content": (
                f"Static review reported {code} at Python line "
                f"{static_review['line']} after applying your proposed edit. "
                "Return only the required JSON edit. Preserve the indentation "
                "and line endings of the original source where needed. Choose a "
                "replacement that changes the reported behavior. Returning the "
                "original lines unchanged will be rejected.\n\n"
                f"Original observed range:\n{original_range}"
            ),
        }
        proposal_messages.append(correction)
        transcript.append({"purpose": "patch_static_review_feedback", **correction})
        event("patch_static_review_retry_requested", attempt=attempt + 2, reason=code)

    raise ValueError("No proposal attempts configured")
