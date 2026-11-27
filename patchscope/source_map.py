"""Source-only, bounded, static import hints for a controlled patch-stage intervention.

No oracle labels, tests, execution, dynamic imports, or runtime call-graph claims.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from patchscope.tools import list_source_files

POLICIES = ("off", "inventory", "imports")


def _module(path: str) -> str:
    parts = Path(path).with_suffix("").parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1])
    return ".".join(parts)


def _candidate(node: ast.ImportFrom, importer: str) -> str | None:
    """Resolve static absolute or relative imports where possible, without execution."""
    if node.level == 0:
        return node.module
    # `from . import foo` is not covered: no fabricated positive edge.
    package = _module(importer).split(".")[:-1]
    up = node.level - 1
    if up > len(package):
        return None
    prefix = package[:len(package)-up] if up else package
    return ".".join([*prefix, *([node.module] if node.module else [])]) or None


def source_reference_map(repo: Path, *, policy: str, max_chars: int = 1400) -> dict:
    """Build a bounded, deterministic, preproposal hint from permitted source files.

    This is a static Python import map, NOT a reliable reachability oracle.
    Missing links are explicitly inconclusive. The inventory is a useful
    presence/format control, but NOT token-length matched to the import map.
    """
    if policy not in POLICIES:
        raise ValueError("invalid_evidence_policy")
    if type(max_chars) is not int or not 300 <= max_chars <= 2400:
        raise ValueError("invalid_source_map_char_budget")
    if policy == "off":
        return {"policy": policy, "text": "", "chars": 0, "sha256": None,
                "files": 0, "static_edges": 0, "truncated": False}
    repo = Path(repo)
    files = sorted(list_source_files(repo))
    modules: dict[str, str] = {}
    for p in files:
        name = _module(p)
        if name:
            modules[name] = p
    edges = set()
    if policy == "imports":
        for importer in files:
            try:
                parsed = ast.parse((repo / importer).read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeError, OSError):
                continue
            for node in ast.walk(parsed):
                refs = []
                if isinstance(node, ast.Import):
                    refs.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    reference = _candidate(node, importer)
                    if reference:
                        refs.append(reference)
                        # imports like `from pkg import util`
                        refs.extend(f"{reference}.{alias.name}" for alias in node.names)
                for ref in refs:
                    # Also handle imported symbols from local module paths:
                    # `from foo.bar import fun` resolves to foo.bar.
                    dest = modules.get(ref)
                    if dest and dest != importer:
                        edges.add((importer, dest))
    prefix = [
        "STATIC REPOSITORY REFERENCE HINT (non-authoritative):",
        "Generated solely from agent-readable non-test source modules; no gold edit labels.",
        "Do not infer runtime reachability from an import. Missing imports are inconclusive.",
        "Only propose exact edits to source text already observed during exploration.",
        "Source files: " + ", ".join(files),
    ]
    if policy == "imports":
        prefix.append("Static source imports (importer -> imported):")
        prefix.extend(f"- {src} -> {dst}" for src, dst in sorted(edges))
        if not edges:
            prefix.append("- No resolvable source-to-source imports; no path is established.")
    else:
        prefix.append("Import relations intentionally withheld in this inventory-only control.")
    out = ""
    truncated = False
    for line in prefix:
        next_line = line + "\n"
        if len(out) + len(next_line) > max_chars:
            # Never fabricate partial graph edges, filename references or imports.
            truncated = True
            break
        out += next_line
    return {"policy": policy, "text": out, "chars": len(out),
            "sha256": hashlib.sha256(out.encode()).hexdigest(),
            "files": len(files), "static_edges": len(edges), "truncated": truncated}
