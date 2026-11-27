"""Post-grading diagnostic for matched SWE-bench Lite development replays."""
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from patchscope.evaluation_git import apply_to_index, git, temporary_patch_index
from patchscope.proposal_windows import describe_replayed_spans
from patchscope.swebench_dev import DATASET, dev_rows, load_prepared, public_task

ARMS = ("baseline", "candidate")
HUNK = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def locations(repo, base, patch):
    """Let Git parse and apply the patch in a disposable index; ignore diff context."""
    if not isinstance(patch, str) or not patch.strip():
        raise ValueError("Empty reference patch")
    changes = []
    with temporary_patch_index(repo) as scratch:
        apply_to_index(scratch, base, patch)
        options = ("diff", "--cached", "--no-renames", "--no-ext-diff", "--no-textconv")
        paths = git(scratch, *options, "--name-only", "-z", base).split(b"\0")
        for raw in filter(None, paths):
            path = raw.decode()
            diff = git(scratch, *options, "--unified=0", "--inter-hunk-context=0",
                       "--diff-algorithm=myers", "--no-indent-heuristic", "--no-color", base, "--", path)
            hunks = HUNK.findall(diff)
            if not git(scratch, "ls-tree", "-z", base, "--", path):
                changes.append((path, "new file", 0, 0))
            elif not hunks:
                changes.append((path, "non-line change", 0, 0))
            else:
                for start, count in hunks:
                    changes.append((path, "text", int(start), int(count or b"1")))
    if not changes:
        raise ValueError("Reference contains no changes against its recorded base")
    return changes


def line_sets(spans, repo, base, *, allow_partial):
    @lru_cache(None)
    def source(path):
        return git(repo, "show", f"{base}:{path}").decode().replace("\r\n", "\n").replace("\r", "\n").splitlines(True)

    seen = defaultdict(set)
    for span in spans:
        path = span["path"]
        first = span.get("start_line", 1)
        pieces = span["content"].splitlines(True)
        if type(first) is not int or first < 1 or not pieces:
            raise ValueError(f"Invalid excerpt for {path}")
        original = source(path)
        for index, piece in enumerate(pieces, first):
            if index > len(original):
                raise ValueError(f"Excerpt exceeds {path} at {index}")
            if original[index - 1] == piece:
                seen[path].add(index)
            elif not (allow_partial and index == first + len(pieces) - 1
                      and original[index - 1].startswith(piece)):
                raise ValueError(f"Excerpt differs from {path} at {index}")
    return seen


def coverage(site, seen):
    path, kind, start, count = site
    if kind != "text":
        return "outside line metric"
    if path not in seen:
        return "path absent"
    if count == 0:
        return "covered" if seen[path].intersection({start, start + 1}) else "outside range"
    hits = sum(line in seen[path] for line in range(start, start + count))
    return "covered" if hits == count else "partial" if hits else "outside range"


def loc(site):
    _, kind, start, count = site
    if kind != "text":
        return kind
    if count == 0:
        return f"gap after line {start}" if start else "gap before line 1"
    return str(start) if count == 1 else f"{start}–{start + count - 1}"


def audit_case(row, replay, exploration, grader_dirs):
    issue = row["instance_id"]
    folders = {arm: replay / arm / issue for arm in ARMS}
    native = folders["baseline"]
    public = load_prepared(native)
    if public != public_task(row):
        raise ValueError(f"{issue}: reference row differs from the prepared task")
    base = public["base_commit"]
    raw = {arm: (folder / "episode.json").read_bytes() for arm, folder in folders.items()}
    episodes = {arm: json.loads(data) for arm, data in raw.items()}
    left, right = episodes["baseline"], episodes["candidate"]
    windows = left["proposal_windows"]
    snapshot = describe_replayed_spans(windows)
    for episode in episodes.values():
        p = episode["provenance"]
        if (episode["task_id"] != issue or p["split"] != "dev" or p["benchmark"] != DATASET
                or p["base_commit"] != base or episode["proposal_source"] != snapshot
                or p["public_issue_sha256"] != digest(public["problem_statement"].encode())
                or p["generation"]["model"] != left["provenance"]["generation"]["model"]):
            raise ValueError(f"{issue}: replay provenance mismatch")
    if right["editor_comparator"]["baseline_episode_sha256"] != digest(raw["baseline"]):
        raise ValueError(f"{issue}: candidate linked to a different baseline")
    original = (exploration / "baseline" / issue / "episode.json").read_bytes()
    if digest(original) != left["provenance"]["exploration_episode_sha256"]:
        raise ValueError(f"{issue}: exploration episode hash mismatch")
    reads = [e["result"] for e in json.loads(original)["trajectory"]
             if e["kind"] == "tool_result" and e["name"] in {"read_file", "read_file_range"}
             and e["result"].get("content")]
    repo = native / "repo"
    held = line_sets(windows, repo, base, allow_partial=False)
    read = line_sets(reads, repo, base, allow_partial=True)
    if any(not lines <= read[path] for path, lines in held.items()):
        raise ValueError(f"{issue}: replay contains lines absent from saved file reads")
    sites = locations(repo, base, row["patch"])
    states = [coverage(s, held) for s in sites]
    summary = "full" if all(s == "covered" for s in states) else (
        "partial" if any(s in {"covered", "partial"} for s in states) else "none")
    if "outside line metric" in states:
        summary += " (includes non-comparable change)"
    details = [f"## {issue}", "", f"Base `{base}`. Shared snapshot `{snapshot['sha256']}`.",
               "", "Shared excerpts", ""]
    for span in snapshot["files"]:
        details.append(f"- `{span['path']}` lines {span['start_line']}–{span['end_line']}")
    details += ["", "| Reference path | Base location | Original file reads | Editing excerpts |",
                "|---|---|---|---|"]
    for site, state in zip(sites, states):
        details.append(f"| `{site[0]}` | {loc(site)} | {coverage(site, read)} | {state} |")
    for arm in ARMS:
        ep = episodes[arm]
        details += ["", f"### {arm.capitalize()}", "", f"Episode outcome `{ep['outcome']['status']}`."]
        if ep.get("error"):
            details.append(f"Episode error `{ep['error']}`.")
        pred = folders[arm] / "prediction.jsonl"
        parent = grader_dirs.get(arm)
        grade = parent / issue / "report.json" if parent else None
        if not pred.exists():
            if grade and grade.exists():
                raise ValueError(f"{issue}: {arm} grade exists without export")
            details.append("No exported prediction.")
            continue
        prediction = json.loads(pred.read_bytes())
        diff = prediction["model_patch"]
        if (not diff or prediction["instance_id"] != issue or diff != ep["proposal_diff"]
                or prediction["model_name_or_path"] != ep["provenance"]["generation"]["model"]):
            raise ValueError(f"{issue}: {arm} prediction mismatch")
        if grade is None or not grade.is_file():
            raise ValueError(f"{issue}: missing official {arm} per-issue report")
        case = json.loads(grade.read_bytes())[issue]
        details += [f"Official applied `{case.get('patch_successfully_applied')}`, "
                    f"resolved `{case.get('resolved')}`.", "",
                    "| Test group | Passed | Failed |", "|---|---:|---:|"]
        tests = case.get("tests_status", {})
        for name, results in tests.items():
            details.append(f"| {name} | {len(results['success'])} | {len(results['failure'])} |")
        if not tests:
            details.append("\nNo per-test outcomes recorded.")
        for name, results in tests.items():
            details.extend(f"- {name} failure: `{test}`" for test in results["failure"])
        details += ["", "Submitted edit", "", "````diff", diff.rstrip("\n"), "````"]
    details += ["", "Public issue", "", public["problem_statement"], "", "Evaluator reference edit",
                "", "````diff", row["patch"].rstrip("\n"), "````", ""]
    read_sites = sum(coverage(site, read) == "covered" for site in sites)
    kept_sites = states.count("covered")
    return summary, f"{read_sites}/{len(sites)}", f"{kept_sites}/{len(sites)}", details


def run(replay, exploration, grader_dirs, rows):
    issues = {p.name for p in (replay / "baseline").iterdir() if p.is_dir()}
    candidates = {p.name for p in (replay / "candidate").iterdir() if p.is_dir()}
    if not issues or issues != candidates:
        raise ValueError("Replay arms have different or empty issue sets")
    rows = [row for row in rows if row["instance_id"] in issues]
    if set(row["instance_id"] for row in rows) != issues or len(rows) != len(issues):
        raise ValueError("Missing or duplicate reference row in development split")
    overview, sections = [], []
    for row in sorted(rows, key=lambda r: r["instance_id"]):
        state, before, after, details = audit_case(row, replay, exploration, grader_dirs)
        overview.append(f"| {row['instance_id']} | {before} | {after} | {state} |")
        sections.extend(details)
    return "\n".join(["# Evaluator-only source-window audit", "",
        "Coverage measures locations in one reference implementation. Other repairs can be valid. "
        "A covered replacement requires all changed base lines. A pure insertion requires either "
        "adjacent line. File reads count only complete lines from read_file and read_file_range. "
        "Search hits are excluded. New files and changes without line coordinates are listed separately.",
        "", "| Development issue | Sites fully covered in reads | Sites fully covered in excerpts | Excerpt coverage |", "|---|---:|---:|---|",
        *overview, "", *sections])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("replay", "exploration", "candidate-grades"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--baseline-grades", type=Path)
    args = parser.parse_args()
    print(run(args.replay, args.exploration,
              {"baseline": args.baseline_grades, "candidate": args.candidate_grades}, dev_rows()))


if __name__ == "__main__":
    main()
