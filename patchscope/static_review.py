"""Conservative, execution-free review of a proposed Python source edit."""
from __future__ import annotations

import ast


def _bound_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                        names.add(child.id)
    return names


def review_python_edit(original: str, changed: str) -> dict:
    """Reject syntax errors and dangling references to removed local bindings."""
    try:
        before = ast.parse(original)
        after = ast.parse(changed)
        compile(after, "<proposed edit>", "exec", dont_inherit=True)
    except SyntaxError as exc:
        return {"passed": False, "code": "python_syntax_invalid",
                "line": exc.lineno, "removed_referenced_bindings": []}
    removed = _bound_names(before) - _bound_names(after)
    loaded_after = {
        node.id for node in ast.walk(after)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    dangling = sorted(removed & loaded_after)
    if dangling:
        return {"passed": False, "code": "removed_binding_still_referenced",
                "line": None, "removed_referenced_bindings": dangling}
    return {"passed": True, "code": "static_review_passed", "line": None,
            "removed_referenced_bindings": []}
