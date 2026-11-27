"""Common full-file inputs for the two development-pilot editors."""
import hashlib
import json
from pathlib import Path
import subprocess

from patchscope.tools import is_test_path, list_source_files

SOURCE_BYTE_LIMIT = 65536


def read_proposal_sources(repo: Path, paths: list[str]) -> tuple[dict[str, bytes], int]:
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError("Invalid observed source paths")
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=repo, text=True,
    ).split("\0"))
    allowed = tracked & set(list_source_files(repo))
    contents = {}
    total = 0
    for path in sorted(set(paths)):
        original = repo / path
        if (path not in allowed or original.resolve() != original
                or is_test_path(path)):
            raise ValueError("Observed path is outside the permitted tracked source set")
        total += original.stat().st_size
        if total > SOURCE_BYTE_LIMIT:
            return {}, total
        contents[path] = original.read_bytes()
    return contents, total


def describe_proposal_sources(contents: dict[str, bytes]) -> dict:
    entries = [
        {"path": path, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        for path, content in sorted(contents.items())
    ]
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {"files": entries, "sha256": hashlib.sha256(encoded).hexdigest()}
