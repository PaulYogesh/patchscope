"""Replay a saved PatchScope line edit against its recorded Git base."""

import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from patchscope.evaluation_git import (
    apply_to_index,
    git,
    grader_patch_matches,
    temporary_patch_index,
)
from patchscope.proposal_contract import materialize_line_edit, normalize_newlines
from patchscope.repair import render_repair_diff


def read_json(path):
    return json.loads(path.read_bytes())


def archived_grade(directory, task_id, patch):
    case = read_json(directory / "report.json")[task_id]
    if not grader_patch_matches(directory, patch):
        raise ValueError(f"No archived grader patch in {directory}")
    if case.get("patch_successfully_applied") is not True:
        raise ValueError("The archived grader did not record successful patch application")
    resolved = case.get("resolved")
    if type(resolved) is not bool:
        raise ValueError("The archived report has no boolean resolution result")
    return {"patch_matches": True, "official_resolved": resolved}


def replay(repo, episode, original):
    base = episode["provenance"]["base_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", base):
        raise ValueError("The episode must record a full base commit hash")

    proposal = episode["proposal"]
    if not isinstance(proposal, dict) or not isinstance(proposal.get("replacement"), str):
        raise ValueError("The episode must contain a saved line-range proposal")
    path = proposal["path"]
    relative = PurePosixPath(path)
    if (not relative.parts or relative.is_absolute() or ".." in relative.parts
            or relative.as_posix() != path or any(char in path for char in "\0\r\n\t")):
        raise ValueError("Invalid proposal path")
    if not original.strip():
        raise ValueError("The original diff is empty")

    entry = git(repo, "ls-tree", "--full-tree", base, "--", path)
    mode = entry.split(maxsplit=1)[0] if entry else b""
    if mode not in (b"100644", b"100755"):
        raise ValueError("The proposal must target a regular file at the recorded base")

    source = git(repo, "show", f"{base}:{path}").decode("utf-8")
    _, intended = materialize_line_edit(proposal, source)
    corrected = render_repair_diff(path, source, intended)
    if not corrected:
        raise ValueError("The proposal does not change the pinned source")

    normalized = normalize_newlines(source)
    _, legacy_intended = materialize_line_edit(proposal, normalized)
    legacy = "".join(difflib.unified_diff(
        normalized.splitlines(keepends=True),
        legacy_intended.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )).encode("utf-8")

    original_tree = None
    original_rejection = None
    with temporary_patch_index(repo) as index:
        git(index, "read-tree", base)
        blob = git(index, "hash-object", "-w", "--stdin",
                   data=intended.encode("utf-8")).decode().strip()
        git(index, "update-index", "--cacheinfo", f"{mode.decode()},{blob},{path}")
        intended_tree = git(index, "write-tree").decode().strip()

        apply_to_index(index, base, corrected)
        corrected_tree = git(index, "write-tree").decode().strip()
        if corrected_tree != intended_tree:
            raise ValueError("The corrected export did not reproduce the intended tree")

        git(index, "read-tree", base)
        try:
            git(index, "apply", "--cached", "--check", "-", data=original)
        except ValueError as error:
            original_rejection = str(error)
        else:
            git(index, "apply", "--cached", "-", data=original)
            original_tree = git(index, "write-tree").decode().strip()

    return corrected, {
        "base_commit": base,
        "path": path,
        "new_model_calls": 0,
        "original_patch_sha256": hashlib.sha256(original).hexdigest(),
        "legacy_renderer_reproduces_original_bytes": original == legacy,
        "original_git_rejection": original_rejection,
        "original_tree": original_tree,
        "original_matches_intended_tree": (
            None if original_tree is None else original_tree == intended_tree
        ),
        "corrected_patch_sha256": hashlib.sha256(corrected.encode("utf-8")).hexdigest(),
        "intended_tree": intended_tree,
        "corrected_tree": corrected_tree,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--original-diff", type=Path, help="Defaults to the episode's saved diff")
    parser.add_argument("--grader-dir", type=Path, help="Directory with report.json and patch.diff")
    parser.add_argument("--write-patch", type=Path, help="Write the corrected patch to a new file")
    args = parser.parse_args()
    try:
        episode = read_json(args.episode)
        if args.original_diff:
            original = args.original_diff.read_bytes()
        else:
            saved_diff = episode["proposal_diff"]
            if not isinstance(saved_diff, str):
                raise ValueError("The episode has no saved diff. Supply --original-diff.")
            original = saved_diff.encode("utf-8")
        corrected, report = replay(args.repo, episode, original)
        report["archived_grade"] = (
            archived_grade(args.grader_dir, episode["task_id"], corrected)
            if args.grader_dir else None
        )
        if args.write_patch:
            with args.write_patch.open("xb") as patch_file:
                patch_file.write(corrected.encode("utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Replay failed: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()