from pathlib import Path

from patchscope.retrieval import discover_files


def is_test_path(path: str) -> bool:
    """Identify conventional Python test files and directories."""
    relative = Path(path)
    return relative.name.startswith("test_") or any(
        part.lower() in {"test", "tests", "testing"} for part in relative.parts
    )


def list_source_files(repo_path):
    """List permitted Python source files."""
    root = Path(repo_path).resolve()

    return [
        path.relative_to(root).as_posix()
        for path in discover_files(root)
        if path.resolve().is_relative_to(root)
    ]


def read_source_file(repo_path, relative_path, max_chars=4000):
    """Read a permitted source file without modifying it."""
    root = Path(repo_path).resolve()
    requested = Path(relative_path)

    if (
        requested.is_absolute()
        or ".." in requested.parts
        or not requested.parts
    ):
        raise ValueError("Invalid relative path")

    target = (root / requested).resolve()

    if not target.is_relative_to(root):
        raise ValueError("Path escapes repository")

    permitted = {
        path.resolve()
        for path in discover_files(root)
        if path.resolve().is_relative_to(root)
    }

    if target not in permitted:
        raise ValueError("File is not an allowed source file")

    if max_chars < 1:
        raise ValueError("max_chars must be positive")

    content = target.read_text(encoding="utf-8")

    return {
        "path": target.relative_to(root).as_posix(),
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }
