"""Score frozen public-traceback localization against development reference sites."""
import argparse
import json
from pathlib import Path

from patchscope.proposal_windows import describe_replayed_spans, read_replay_source
from patchscope.swebench_dev import DATASET, INSTANCE_RE, load_prepared, dev_rows, public_task
from patchscope.traceback_windows import traceback_frames, reposition
from scripts.audit_swebench_windows import coverage, digest, line_sets, locations


def describe(window):
    first = window["start_line"]
    last = first + len(window["content"].splitlines()) - 1
    return f"{first}–{last} ({len(window['content'].encode())} B)"


def freeze(folder):
    task = load_prepared(folder)
    episode = json.loads((folder / "episode.json").read_bytes())
    original = episode["proposal_windows"]
    provenance = episode["provenance"]
    issue = task["problem_statement"]
    if (task["instance_id"] != folder.name or episode["task_id"] != folder.name
            or episode["proposal_source"] != describe_replayed_spans(original)
            or provenance["benchmark"] != DATASET or provenance["split"] != "dev"
            or provenance["base_commit"] != task["base_commit"]
            or provenance["public_issue_sha256"] != digest(issue.encode())):
        raise ValueError(f"Episode provenance mismatch: {folder}")
    repo = folder / "repo"
    frames = traceback_frames(issue)
    updated, details = [], []
    for window in original:
        path = window["path"]
        moved, reason = reposition(window, read_replay_source(repo, path), issue, frames)
        updated.append(moved)
        details.append(f"- `{path}` {describe(window)} → {describe(moved)}. {reason}.")
    seen = [line_sets(w, repo, task["base_commit"], allow_partial=False) for w in (original, updated)]
    return task, repo, seen, details


def report(frozen, rows):
    refs = {}
    for row in rows:
        key = row["instance_id"]
        if key in refs:
            raise ValueError(f"Duplicate reference: {key}")
        refs[key] = row
    table = ["# Traceback localization probe", "",
             "| Issue | Sites in old excerpts | Sites in proposed excerpts | Gained | Lost |",
             "|---|---:|---:|---:|---:|"]
    detail = []
    for task, repo, seen, notes in frozen:
        issue = task["instance_id"]
        row = refs[issue]
        if task != public_task(row):
            raise ValueError(f"Reference row differs from frozen task: {issue}")
        sites = locations(repo, task["base_commit"], row["patch"])
        old, new = [{s for s in sites if coverage(s, arm) == "covered"} for arm in seen]
        table.append(f"| {issue} | {len(old)}/{len(sites)} | {len(new)}/{len(sites)} | "
                     f"{len(new - old)} | {len(old - new)} |")
        detail.extend(["", f"## {issue}", "", *notes])
    return "\n".join(table + detail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", required=True, type=Path)
    parser.add_argument("--instances", required=True, nargs="+")
    args = parser.parse_args()
    if (not all(INSTANCE_RE.fullmatch(i) for i in args.instances)
            or len(set(args.instances)) != len(args.instances)):
        parser.error("Expected unique development instance IDs")
    # Construct all source windows before opening the reference dataset.
    frozen = [freeze(args.replay.expanduser().resolve() / "baseline" / i) for i in args.instances]
    print(report(frozen, dev_rows()))


if __name__ == "__main__":
    main()
