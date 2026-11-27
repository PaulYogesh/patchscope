"""Bounded, read-only navigation for large public Python repositories.

Opt-in for external benchmark pilots. Does not execute repository code or
expose test files. Source ranges remain bounded and in exact file order.
"""
from __future__ import annotations

from pathlib import Path

from patchscope.tools import is_test_path, list_source_files


class NavigationError(ValueError):
    pass


def _source(root: Path, path: str) -> Path:
    if not isinstance(path, str) or not path:
        raise NavigationError("invalid source path")
    root = Path(root).resolve()
    if is_test_path(path):
        raise NavigationError("test directories are not readable by navigation")
    if path not in list_source_files(root):
        raise NavigationError("path is not an allowed source file")
    target = (root / path).resolve()
    if not target.is_file() or not target.is_relative_to(root):
        raise NavigationError("path escapes source tree")
    if is_test_path(target.relative_to(root)):
        raise NavigationError("test directories are not readable by navigation")
    return target


def read_file_range(root: Path, path: str, start_line: int, end_line: int) -> dict:
    """Inclusive 1-indexed range; at most 60 lines and 3500 characters."""
    if (type(start_line) is not int or type(end_line) is not int
            or start_line < 1 or end_line < start_line
            or end_line - start_line + 1 > 60):
        raise NavigationError("invalid line range; request 1-60 lines")
    target = _source(root, path)
    # Avoid accidentally loading huge generated source files into memory.
    if target.stat().st_size > 2_000_000:
        raise NavigationError("source file exceeds pilot size limit")
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    if start_line > len(lines):
        raise NavigationError(f"start_line beyond EOF; total_lines={len(lines)}")
    code = "".join(lines[start_line - 1:end_line])
    truncated = len(code) > 3500
    return {
        "path": path, "start_line": start_line,
        "end_line": min(end_line, len(lines)), "total_lines": len(lines),
        "content": code[:3500], "truncated": truncated,
    }


def search_code(root: Path, query: str) -> dict:
    """Literal substring search, capped at 8 hits, 400 source files and 100k lines."""
    if not isinstance(query, str) or not 2 <= len(query) <= 100 or "\n" in query:
        raise NavigationError("query must be a 2-100 character single-line literal")
    hits = []
    files_scanned = 0
    lines_scanned = 0
    root = Path(root).resolve()
    query_folded = query.casefold()
    for path in list_source_files(root):
        # No test files, nor conventional test directories, in navigation.
        if is_test_path(path):
            continue
        if files_scanned >= 400 or lines_scanned >= 100_000:
            break
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file() or is_test_path(target.relative_to(root)):
            continue
        if target.stat().st_size > 200_000:
            continue
        files_scanned += 1
        with target.open(encoding="utf-8") as f:
            for number, line in enumerate(f, start=1):
                lines_scanned += 1
                if query_folded in line.casefold():
                    hits.append({"path": path, "line": number, "text": line.strip()[:180]})
                    if len(hits) >= 8:
                        return {"query": query, "hits": hits, "limit_reached": True}
                if lines_scanned >= 100_000:
                    break
    return {"query": query, "hits": hits, "limit_reached": files_scanned >= 400 or lines_scanned >= 100_000}
