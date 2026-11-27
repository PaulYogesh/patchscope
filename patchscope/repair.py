import difflib
import io
import shutil
import subprocess
import sys
import tempfile

from contextlib import contextmanager
from pathlib import Path

from patchscope.proposal_contract import ProposalContractError, materialize_line_edit, normalize_newlines
from patchscope.tools import list_source_files


def render_repair_diff(path: str, original: str, changed: str) -> str:
    """Render a Git-applicable text diff, including unterminated source lines."""
    lines = difflib.unified_diff(
        io.StringIO(original).readlines(), io.StringIO(changed).readlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    )
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in lines
    )


@contextmanager
def temporary_repo(source_repo):
    """Make a disposable copy of a trusted test repository."""
    source = Path(source_repo).resolve()

    if not source.is_dir():
        raise ValueError("Repository does not exist")

    with tempfile.TemporaryDirectory(
        prefix="patchscope-"
    ) as temp_dir:
        workdir = Path(temp_dir) / "repo"
        shutil.copytree(source, workdir)

        yield workdir


def apply_exact_edit(repo_path, relative_path, old, new):
    """Replace exactly one matching source-code fragment."""
    root = Path(repo_path).resolve()

    if not isinstance(relative_path, str):
        raise ValueError("Path must be a string")

    allowed_files = set(list_source_files(root))

    if relative_path not in allowed_files:
        raise ValueError("File is not approved for editing")

    if not isinstance(old, str) or not isinstance(new, str):
        raise ValueError("Edit fragments must be strings")

    if not old or old == new:
        raise ValueError("Edit must make a real change")

    if len(old) > 4000 or len(new) > 4000:
        raise ValueError("Edit exceeds size limit")

    target = (root / relative_path).resolve()

    if not target.is_relative_to(root):
        raise ValueError("Path escapes repository")

    original = target.read_text(encoding="utf-8")

    if original.count(old) != 1:
        raise ValueError(
            "Expected exactly one matching code fragment"
        )

    modified = original.replace(old, new, 1)
    target.write_text(modified, encoding="utf-8")

    return {"path": relative_path, "applied": True}


def apply_line_edit(repo_path, proposal):
    """Apply one hash-bound line edit after validating the current source."""
    root = Path(repo_path).resolve()
    required = {"path", "start_line", "end_line", "replacement", "expected_sha256"}
    if not isinstance(proposal, dict) or set(proposal) != required:
        raise ValueError("Invalid line edit proposal")
    path = proposal["path"]
    if path not in set(list_source_files(root)):
        raise ValueError("File is not approved for editing")
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path escapes repository")
    source = target.read_bytes().decode("utf-8")
    lines = source.splitlines(keepends=True)
    start, end = proposal["start_line"], proposal["end_line"]
    if (type(start) is not int or type(end) is not int
            or start < 1 or end < start or end > len(lines)):
        raise ValueError("Invalid line edit range")
    old = "".join(lines[start - 1:end])
    replacement = proposal["replacement"]
    if (not isinstance(replacement, str) or len(replacement) > 4000
            or normalize_newlines(replacement) == normalize_newlines(old)):
        raise ValueError("Line edit replacement is invalid")
    try:
        _, changed = materialize_line_edit(proposal, source)
    except ProposalContractError as exc:
        if exc.code == "patch_source_hash_mismatch":
            raise ValueError("Line edit source hash mismatch") from exc
        raise
    target.write_bytes(changed.encode("utf-8"))
    return {"path": path, "applied": True, "expected_sha256": proposal["expected_sha256"]}


def run_pytest(repo_path, timeout=30):
    """Run tests in a trusted local fixture repository."""
    with tempfile.TemporaryDirectory(prefix="patchscope-pycache-") as cache_dir:
        completed = subprocess.run(
            [sys.executable, "-B", "-X", f"pycache_prefix={cache_dir}", "-m", "pytest", "-q"],
            cwd=Path(repo_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    return {
        "passed": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": (
            completed.stdout + completed.stderr
        )[-1500:],
    }
