"""Run provenance without recording credentials or environment secrets."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from patchscope.experiment import manifest_sha256
from patchscope.protocol import TOOLS

PROMPT_VERSION = "patchscope-agent-v023-001"


def _ollama(base_url: str, endpoint: str, payload=None) -> dict:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {"error": "unsupported_model_endpoint"}
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return {"error": "only_local_ollama_provenance_supported"}
    base = f"{parsed.scheme}://{parsed.netloc}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base + endpoint, data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.HTTPError):
        return {"error": "ollama_endpoint_unavailable"}


def source_tree_sha256(root: Path) -> str:
    """Fingerprint experimental code, tests and fixtures, including uncommitted edits.

    Git HEAD alone can be misleading when applying a ZIP overlay. The digest
    covers bytes under relevant project directories, independent of mtimes.
    """
    relevant = []
    for folder in ("patchscope", "scripts", "tests", "fixtures", "reproducers"):
        base = root / folder
        if base.exists():
            relevant.extend(f for f in base.rglob("*") if f.is_file()
                            and f.suffix in {".py", ".md", ".json"}
                            and not any(part.startswith(".") or part == "__pycache__"
                                        for part in f.relative_to(root).parts))
    requirements = root / "requirements.txt"
    if requirements.is_file():
        relevant.append(requirements)
    digest = hashlib.sha256()
    for path in sorted(set(relevant)):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def capture_provenance(root: Path, manifest: dict, model: str, base_url: str) -> dict:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, check=False)
    worktree = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                              cwd=root, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, check=False)
    version = _ollama(base_url, "/api/version")
    tags = _ollama(base_url, "/api/tags")
    show = _ollama(base_url, "/api/show", {"model": model})
    listed = next((item for item in tags.get("models", [])
                   if item.get("name") == model or item.get("model") == model), {})
    return {
        "git_commit": proc.stdout.strip() if proc.returncode == 0 else "unavailable_source_archive",
        "git_worktree_dirty": (bool(worktree.stdout.strip()) if worktree.returncode == 0 else None),
        "source_tree_sha256": source_tree_sha256(root),
        "manifest_sha256": manifest_sha256(manifest),
        "prompt_version": PROMPT_VERSION,
        "tool_schema_sha256": hashlib.sha256(
            json.dumps(TOOLS, sort_keys=True).encode()).hexdigest(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "ollama": {
            "version": version.get("version", "unavailable"),
            "model": model,
            "digest": listed.get("digest", "unavailable"),
            "parameter_size": listed.get("details", {}).get("parameter_size"),
            "quantization_level": listed.get("details", {}).get("quantization_level"),
            "capabilities": show.get("capabilities", []),
        },
    }
