"""Strict tool protocol; textual fallback only in explicitly marked compatibility runs."""
from __future__ import annotations

import json
from dataclasses import dataclass

TOOL_MODE_NATIVE_REQUIRED = "native_required"
TOOL_MODE_FALLBACK_ALLOWED = "fallback_allowed"

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List readable Python implementation files (not tests).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read one source-code file by relative path (not tests).",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    }},
]


# Opt-in for large repository navigation; original TOOL definitions stay fixed.
TOOLS_NAVIGATION = TOOLS + [
    {"type": "function", "function": {
        "name": "read_file_range",
        "description": "Read an exact 1-indexed range (1-60 lines) from an allowed Python source file. Use around traceback lines.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        }, "required": ["path", "start_line", "end_line"], "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "search_code",
        "description": "Search allowed repository source files for a short literal string; returns file paths and line numbers.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
        }, "required": ["query"], "additionalProperties": False},
    }},
]


class ToolProtocolError(ValueError):
    pass


class RangedReadProtocolError(ToolProtocolError):
    """A single rejected native read_file call can receive a tool reply."""

    def __init__(self, *, call_id: str, path: str):
        super().__init__("Unapproved tool or arguments: 'read_file'")
        self.call_id = call_id
        self.path = path


@dataclass(frozen=True)
class ToolAction:
    name: str
    arguments: dict
    mode: str
    call_id: str | None = None


def parse_json_dict(text: str | None) -> dict | None:
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        raw = raw[len("```json\n"):-len("\n```")]
    elif raw.startswith("```\n") and raw.endswith("\n```"):
        raw = raw[len("```\n"):-len("\n```")]
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def validate_action(name: object, args: object) -> tuple[str, dict]:
    if name == "list_files" and isinstance(args, dict) and not args:
        return name, args
    if (name == "read_file" and isinstance(args, dict)
            and set(args) == {"path"} and isinstance(args["path"], str)
            and bool(args["path"])):
        return name, args
    if (name == "read_file_range" and isinstance(args, dict)
            and set(args) == {"path", "start_line", "end_line"}
            and isinstance(args["path"], str) and bool(args["path"])
            and type(args["start_line"]) is int and type(args["end_line"]) is int):
        return name, args
    if (name == "search_code" and isinstance(args, dict)
            and set(args) == {"query"} and isinstance(args["query"], str)):
        return name, args
    raise ToolProtocolError(f"Unapproved tool or arguments: {name!r}")


def decode_message(
    message, *, mode: str, allowed_tools=None, recover_ranged_read: bool = False,
) -> tuple[list[ToolAction], str | None]:
    """(actions, final_text). Raise on invalid or prohibited tool requests."""
    if mode not in {TOOL_MODE_NATIVE_REQUIRED, TOOL_MODE_FALLBACK_ALLOWED}:
        raise ValueError("Unknown tool policy")
    native_calls = getattr(message, "tool_calls", None) or []
    if native_calls:
        actions = []
        seen_ids = set()
        for call in native_calls:
            if getattr(call, "type", "function") != "function":
                raise ToolProtocolError("Non-function tool call")
            call_id = getattr(call, "id", None)
            if not isinstance(call_id, str) or not call_id or call_id in seen_ids:
                raise ToolProtocolError("Missing or duplicate native tool_call_id")
            seen_ids.add(call_id)
            fn = getattr(call, "function", None)
            if fn is None:
                raise ToolProtocolError("Malformed native tool call")
            args = parse_json_dict(getattr(fn, "arguments", None))
            name = getattr(fn, "name", None)
            if (recover_ranged_read and len(native_calls) == 1
                    and allowed_tools is not None
                    and {"read_file", "read_file_range"} <= set(allowed_tools)
                    and name == "read_file" and args is not None
                    and set(args) == {"path", "start_line", "end_line"}
                    and isinstance(args["path"], str) and args["path"]):
                raise RangedReadProtocolError(call_id=call_id, path=args["path"])
            name, args = validate_action(name, args)
            if allowed_tools is not None and name not in allowed_tools:
                raise ToolProtocolError(f"Tool not enabled in this experiment: {name}")
            actions.append(ToolAction(name, args, "native", call_id))
        return actions, None

    content = getattr(message, "content", None)
    text_request = parse_json_dict(content)
    if isinstance(text_request, dict) and set(text_request) == {"name", "arguments"}:
        if mode == TOOL_MODE_NATIVE_REQUIRED:
            raise ToolProtocolError("tool_protocol_violation: textual tool request under native_required")
        name, args = validate_action(text_request["name"], text_request["arguments"])
        if allowed_tools is not None and name not in allowed_tools:
            raise ToolProtocolError(f"Tool not enabled in this experiment: {name}")
        return [ToolAction(name, args, "validated_text_fallback")], None
    # Even in primary experiments, ordinary final prose is a legal response.
    return [], content


def assistant_message(message) -> dict:
    """Serialize native tool calls with their real IDs, never fabricate IDs."""
    data = {"role": "assistant", "content": getattr(message, "content", None)}
    native = getattr(message, "tool_calls", None) or []
    if native:
        data["tool_calls"] = [
            {"id": call.id, "type": "function",
             "function": {"name": call.function.name, "arguments": call.function.arguments}}
            for call in native
        ]
    return data
