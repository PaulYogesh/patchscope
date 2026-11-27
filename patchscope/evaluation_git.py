"""Read evaluator patch evidence using disposable Git state."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


def git(repo, *args, data=None):
    result = subprocess.run(["git", "--literal-pathspecs", "-C", str(repo), *args],
                            input=data, capture_output=True)
    if result.returncode:
        raise ValueError(f"Git {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


@contextmanager
def temporary_patch_index(repo):
    repo = Path(repo).resolve()
    with TemporaryDirectory() as directory:
        scratch = Path(directory) / "evaluation.git"
        git(repo, "clone", "--quiet", "--bare", "--local", "--shared", str(repo), str(scratch))
        yield scratch


def apply_to_index(index, base, patch):
    git(index, "read-tree", base)
    git(index, "apply", "--cached", "--whitespace=nowarn", "-", data=patch.encode("utf-8"))


def grader_patch_matches(folder, patch):
    """Check grader output when an archived copy of its input patch exists."""
    path = folder / "patch.diff"
    if not path.is_file():
        return False
    expected = patch.encode("utf-8")
    if path.read_bytes() not in (expected, expected + b"\n"):
        raise ValueError(f"{path}: grader patch differs from prediction")
    return True
