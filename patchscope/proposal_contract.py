"""Strict repair-contract inspection; never execute or auto-correct generated code.

Inspection is intentionally conservative: invalid source JSON requires a fresh
model response, not substring extraction or guessing a patch from prose.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from patchscope.protocol import parse_json_dict
from patchscope.tools import list_source_files


class ProposalContractError(ValueError):
    """Precise machine-readable rejection of a patch proposal."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


LEGACY_CONTRACT = "exact_fragment_v1"
LINE_CONTRACT = "line_range_hash_v1"


def normalize_newlines(text: str) -> str:
    """Use the same line endings as repository tools and saved observations."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _line_slice(text: str, start_line: int, end_line: int) -> str:
    """Return an inclusive 1-indexed line slice, preserving line endings."""
    lines = text.splitlines(keepends=True)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ProposalContractError("patch_line_range_invalid")
    return "".join(lines[start_line - 1:end_line])


def _check_line_boundary(replacement: str, *, has_following_lines: bool) -> None:
    if has_following_lines and replacement and not replacement.endswith(("\n", "\r")):
        raise ProposalContractError("patch_replacement_missing_final_newline")


def observed_span(path: str, start_line: int, content: str) -> dict:
    """Create an auditable observation span from content actually shown."""
    if not isinstance(content, str) or not content:
        raise ValueError("observed span content must be nonempty")
    return {
        "path": path,
        "start_line": start_line,
        "content": content,
    }


def _range_was_observed(*, path: str, start_line: int, old: str,
                        spans: list[dict]) -> bool:
    """Require the complete replacement target to occur in one displayed span."""
    old_lines = old.splitlines(keepends=True)
    if not old_lines:
        return False
    for span in spans:
        if span.get("path") != path or type(span.get("start_line")) is not int:
            continue
        offset = start_line - span["start_line"]
        if offset < 0:
            continue
        shown = span.get("content")
        if not isinstance(shown, str):
            continue
        shown_lines = shown.splitlines(keepends=True)
        candidate = "".join(shown_lines[offset:offset + len(old_lines)])
        if candidate == old:
            return True
    return False


def render_observed_spans(spans: list[dict]) -> str:
    """Render exact displayed evidence with stable, explicit line numbers."""
    blocks = []
    for span in spans:
        content = span["content"]
        start = span["start_line"]
        numbered = "".join(
            f"{number:>6}: {line}"
            for number, line in enumerate(content.splitlines(keepends=True), start=start)
        )
        if content and not content.endswith(("\n", "\r")):
            numbered += "\n"
        blocks.append(f"FILE: {span['path']} (observed from line {start})\n{numbered}")
    return "\n\n".join(blocks)


def inspect_proposal_text(text: str | None) -> dict:
    """Content-free structure diagnosis, safe for summaries of old run logs."""
    parsed = parse_json_dict(text)
    if parsed is None:
        return {"valid_json_object": False, "code": "patch_json_invalid_or_missing",
                "fields": [], "response_chars": len(text) if isinstance(text, str) else 0}
    fields = sorted(key for key in parsed if key in {"path", "old", "new"})
    unexpected_fields = sum(key not in {"path", "old", "new"} for key in parsed)
    if set(parsed) != {"path", "old", "new"}:
        code = "patch_fields_invalid"
    elif any(not isinstance(parsed[k], str) for k in ("path", "old", "new")):
        code = "patch_field_types_invalid"
    elif not parsed["old"] or parsed["old"] == parsed["new"]:
        code = "patch_edit_empty_or_unchanged"
    elif len(parsed["old"]) > 4000 or len(parsed["new"]) > 4000:
        code = "patch_edit_too_large"
    else:
        code = "structure_valid"
    return {"valid_json_object": True, "code": code,
            "fields": fields, "unexpected_field_count": unexpected_fields, "response_chars": len(text) if isinstance(text, str) else 0}


def inspect_line_proposal_text(text: str | None) -> dict:
    """Content-free diagnostics for the v0.9 line-range contract."""
    parsed = parse_json_dict(text)
    allowed = {"path", "start_line", "end_line", "replacement"}
    if parsed is None:
        return {"valid_json_object": False, "code": "patch_json_invalid_or_missing",
                "fields": [], "response_chars": len(text) if isinstance(text, str) else 0}
    fields = sorted(key for key in parsed if key in allowed)
    if set(parsed) != allowed:
        code = "patch_fields_invalid"
    elif (not isinstance(parsed["path"], str)
          or type(parsed["start_line"]) is not int
          or type(parsed["end_line"]) is not int
          or not isinstance(parsed["replacement"], str)):
        code = "patch_field_types_invalid"
    elif parsed["start_line"] < 1 or parsed["end_line"] < parsed["start_line"]:
        code = "patch_line_range_invalid"
    elif len(parsed["replacement"]) > 4000:
        code = "patch_edit_too_large"
    else:
        code = "structure_valid"
    return {"valid_json_object": True, "code": code, "fields": fields,
            "unexpected_field_count": sum(key not in allowed for key in parsed),
            "response_chars": len(text) if isinstance(text, str) else 0}


def validate_proposal(proposal: dict | None, observed: dict[str, str], repo: Path) -> dict:
    """Only permit a single exact edit to uniquely observed implementation code."""
    if not isinstance(proposal, dict):
        raise ProposalContractError("patch_json_invalid_or_missing")
    if set(proposal) != {"path", "old", "new"}:
        raise ProposalContractError("patch_fields_invalid")
    if any(not isinstance(proposal[k], str) for k in ("path", "old", "new")):
        raise ProposalContractError("patch_field_types_invalid")
    path, old, new = (proposal[k] for k in ("path", "old", "new"))
    if path not in observed or path not in list_source_files(repo):
        raise ProposalContractError("patch_path_not_observed_or_disallowed")
    if not old or new == old:
        raise ProposalContractError("patch_edit_empty_or_unchanged")
    if len(old) > 4000 or len(new) > 4000:
        raise ProposalContractError("patch_edit_too_large")
    if observed[path].count(old) != 1:
        raise ProposalContractError("patch_old_not_unique_in_observed")
    if (repo / path).read_text(encoding="utf-8").count(old) != 1:
        raise ProposalContractError("patch_old_not_unique_in_source")
    return proposal


def validate_line_proposal(proposal: dict | None, observed_spans: list[dict],
                           repo: Path) -> dict:
    """Validate one line-addressed edit and bind it to the observed source hash.

    The model supplies line coordinates and replacement text. PatchScope derives
    the original text and its hash from the immutable repository; model-authored
    hashes are deliberately not accepted.
    """
    required = {"path", "start_line", "end_line", "replacement"}
    if not isinstance(proposal, dict):
        raise ProposalContractError("patch_json_invalid_or_missing")
    if set(proposal) != required:
        raise ProposalContractError("patch_fields_invalid")
    path = proposal["path"]
    start_line = proposal["start_line"]
    end_line = proposal["end_line"]
    replacement = proposal["replacement"]
    if (not isinstance(path, str) or type(start_line) is not int
            or type(end_line) is not int or not isinstance(replacement, str)):
        raise ProposalContractError("patch_field_types_invalid")
    if path not in {span.get("path") for span in observed_spans} or path not in list_source_files(repo):
        raise ProposalContractError("patch_path_not_observed_or_disallowed")
    if start_line < 1 or end_line < start_line or end_line - start_line + 1 > 60:
        raise ProposalContractError("patch_line_range_invalid")
    if len(replacement) > 4000:
        raise ProposalContractError("patch_edit_too_large")
    source = (repo / path).read_text(encoding="utf-8")
    old = _line_slice(source, start_line, end_line)
    if normalize_newlines(replacement) == old:
        raise ProposalContractError("patch_edit_empty_or_unchanged")
    if not _range_was_observed(path=path, start_line=start_line, old=old,
                               spans=observed_spans):
        raise ProposalContractError("patch_range_not_fully_observed")
    _check_line_boundary(replacement, has_following_lines=end_line < len(source.splitlines()))
    return {
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "replacement": replacement,
        "expected_sha256": hashlib.sha256(old.encode("utf-8")).hexdigest(),
    }


def materialize_line_edit(proposal: dict, source: str) -> tuple[str, str]:
    """Return (old, changed) after rechecking the v0.9 content binding."""
    original_range = _line_slice(source, proposal["start_line"], proposal["end_line"])
    old = normalize_newlines(original_range)
    actual = hashlib.sha256(old.encode("utf-8")).hexdigest()
    if actual != proposal.get("expected_sha256"):
        raise ProposalContractError("patch_source_hash_mismatch")
    lines = source.splitlines(keepends=True)
    _check_line_boundary(proposal["replacement"],
                         has_following_lines=proposal["end_line"] < len(lines))
    line_ending = re.search(r"\r\n?|\n", original_range) or re.search(r"\r\n?|\n", source)
    newline = line_ending.group() if line_ending else "\n"
    replacement = normalize_newlines(proposal["replacement"]).replace("\n", newline)
    changed = "".join(
        lines[:proposal["start_line"] - 1]
        + [replacement]
        + lines[proposal["end_line"]:]
    )
    return old, changed
