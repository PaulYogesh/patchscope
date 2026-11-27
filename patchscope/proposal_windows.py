"""Recover bounded, byte-checked edits from the source already read in a saved episode."""
import hashlib
import json
from pathlib import Path

from patchscope.proposal_contract import materialize_line_edit, normalize_newlines, observed_span
from patchscope.tools import is_test_path, list_source_files

WINDOW_BYTE_LIMIT = 8192
WINDOW_LINE_LIMIT = 60


def read_replay_source(repo: Path, path: str, *, preserve_newlines: bool = False) -> str:
    target = repo / path
    if (path not in set(list_source_files(repo)) or target.resolve() != target
            or is_test_path(path)):
        raise ValueError(f"Replay source path is not a permitted implementation file: {path}")
    content = target.read_bytes().decode("utf-8")
    return content if preserve_newlines else normalize_newlines(content)


def select_replayed_spans(repo: Path, episode: dict) -> list[dict]:
    """Prefer recent explicit reads, then prefixes. Keep one window per file."""
    allowed_paths = set(episode["observed_paths"])
    reads = [
        event for event in reversed(episode["trajectory"])
        if event["kind"] == "tool_result" and event["name"] in {"read_file_range", "read_file"}
        and event["result"].get("path") in allowed_paths and event["result"].get("content")
    ]
    reads.sort(key=lambda event: event["name"] != "read_file_range")
    windows = {}
    remaining = WINDOW_BYTE_LIMIT
    for event in reads:
        result = event["result"]
        path = result["path"]
        if path in windows:
            continue
        start = result.get("start_line", 1)
        if type(start) is not int or start < 1:
            raise ValueError("Invalid line in saved read")
        original = read_replay_source(repo, path).splitlines(keepends=True)
        chunk = result["content"]
        lines = original[start - 1:start - 1 + WINDOW_LINE_LIMIT]
        chosen = []
        offset = 0
        for line in lines:
            size = len(line.encode("utf-8"))
            if not chunk.startswith(line, offset) or size > remaining:
                break
            chosen.append(line)
            offset += len(line)
            remaining -= size
        if chosen:
            windows[path] = observed_span(path, start, "".join(chosen))
        if len(windows) == 3:
            break
    return list(windows.values())


def describe_replayed_spans(windows: list[dict]) -> dict:
    entries = [
        {"path": span["path"], "start_line": span["start_line"],
         "end_line": span["start_line"] + len(span["content"].splitlines()) - 1,
         "sha256": hashlib.sha256(span["content"].encode()).hexdigest()}
        for span in windows
    ]
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {"files": entries, "sha256": hashlib.sha256(encoded).hexdigest(),
            "policy": "replayed_windows_v1"}


def lift_replayed_edit(repo: Path, span: dict, replacement: str) -> tuple[str, str]:
    """Splice exactly one staged window back into the complete unchanged file."""
    original = read_replay_source(repo, span["path"], preserve_newlines=True)
    start = span["start_line"]
    end = start + len(span["content"].splitlines()) - 1
    proposal = {"start_line": start, "end_line": end, "replacement": replacement,
                "expected_sha256": hashlib.sha256(span["content"].encode()).hexdigest()}
    _, changed = materialize_line_edit(proposal, original)
    return original, changed
