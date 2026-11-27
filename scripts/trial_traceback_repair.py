"""Run a four-issue native repair comparison on the full SWE-bench dev split."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from patchscope.proposal_windows import describe_replayed_spans
from patchscope.swebench_dev import (
    FULL_DEV_DATASET, PUBLIC_KEYS, load_prepared, prepare_dev_instance, public_task, run_local_pilot,
)
from patchscope.traceback_windows import traceback_frames
from scripts.replay_swebench_windows import run_native_replay

MODEL = "qwen3.5:9b"
POLICIES = {"baseline": "saved_reads_v1", "candidate": "traceback_v1"}
EXCLUSIONS = Path(__file__).resolve().parents[1] / "reports/swebench-lite-dev-23.txt"


def select_tasks(rows, excluded):
    eligible = [public_task(row) for row in rows if row["instance_id"] not in excluded
                and traceback_frames(row["problem_statement"])]
    ranked = sorted(eligible, key=lambda row: hashlib.sha256(
        ("patchscope-traceback-v1/" + row["instance_id"]).encode()).hexdigest())
    tasks = ranked[:4]
    if len(tasks) != 4 or len({row["instance_id"] for row in tasks}) != 4:
        raise ValueError("Expected four distinct eligible dev issues")
    return tasks


def freeze(root):
    path = root / "protocol.json"
    if path.exists():
        return json.loads(path.read_bytes())
    from datasets import load_dataset
    data = load_dataset(FULL_DEV_DATASET, split="dev").select_columns(list(PUBLIC_KEYS))
    excluded = set(EXCLUSIONS.read_text().split())
    tasks = select_tasks(data, excluded)
    protocol = {"dataset": FULL_DEV_DATASET, "split": "dev", "model": MODEL, "excluded": sorted(excluded),
                "policies": POLICIES, "eligible_subset": "public Python tracebacks",
                "primary_outcome": "officially resolved per assigned issue", "tasks": tasks}
    write_json(path, protocol)
    return protocol


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def generate(root):
    from openai import OpenAI
    from patchscope.llm import get_config

    protocol = freeze(root)
    if (protocol["dataset"], protocol["split"], protocol["model"], protocol["policies"]) != (
            FULL_DEV_DATASET, "dev", MODEL, POLICIES):
        raise ValueError("Unexpected frozen settings")
    tasks = protocol["tasks"]
    ids = [task["instance_id"] for task in tasks]
    if len(ids) != 4 or len(set(ids)) != 4 or set(ids) & set(EXCLUSIONS.read_text().split()):
        raise ValueError("Invalid frozen cohort")
    (root / "instances.txt").write_text("\n".join(ids) + "\n")
    print("Frozen cohort:", ", ".join(ids), flush=True)
    config = get_config()
    client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=180, max_retries=0)
    for index, task in enumerate(tasks):
        issue = task["instance_id"]
        source = root / "exploration" / issue
        if not source.exists():
            prepare_dev_instance(task, source.parent)
        if load_prepared(source) != task:
            raise ValueError("Stored exploration differs from frozen task")
        if not (source / "episode.json").exists():
            print("Shared exploration:", issue, flush=True)
            run_local_pilot(source, model=MODEL, benchmark=FULL_DEV_DATASET, behavioral_proposal=True,
                            file_inventory_limit=40, proposal_reasoning_effort="none")
        order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        for arm in order:
            parent = root / arm
            parent.mkdir(exist_ok=True)
            if not (parent / issue).exists():
                print(arm, issue, flush=True)
                with tempfile.TemporaryDirectory(dir=parent) as staging:
                    run_native_replay(source, Path(staging), client=client, benchmark=FULL_DEV_DATASET,
                                      traceback_policy=arm == "candidate")
                    (Path(staging) / issue).rename(parent / issue)
    return validate(root, tasks)


def validate(root, tasks):
    lines = ["# Traceback repair trial", "",
             "Both arms use the native editor. Editing costs exclude shared exploration. "
             "Changed means the actual editing excerpt differed.", "",
             "| Issue | Changed | Baseline export | Candidate export |", "|---|---|---|---|"]
    for task in tasks:
        issue = task["instance_id"]
        source = root / "exploration" / issue / "episode.json"
        parent_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        issue_hash = hashlib.sha256(task["problem_statement"].encode()).hexdigest()
        episodes = []
        for arm, policy in POLICIES.items():
            ep = json.loads((root / arm / issue / "episode.json").read_bytes())
            p = ep["provenance"]
            if (p["window_policy"] != policy or p["exploration_episode_sha256"] != parent_hash
                    or p["benchmark"] != FULL_DEV_DATASET or p["split"] != "dev" or ep["task_id"] != issue
                    or p["base_commit"] != task["base_commit"] or p["public_issue_sha256"] != issue_hash
                    or p["generation"]["model"] != MODEL or ep["usage"]["tool_calls"] != 0):
                raise ValueError(f"{issue}: inconsistent {arm} provenance")
            windows = ep["proposal_windows"]
            snapshot = describe_replayed_spans(windows) if windows else None
            if snapshot != ep["proposal_source"]:
                raise ValueError(f"{issue}: source hash mismatch")
            episodes.append(ep)
        old, new = episodes
        if old["budgets"] != new["budgets"] or old["provenance"]["generation"] != new["provenance"]["generation"]:
            raise ValueError(f"{issue}: paired settings differ")
        left, right = old["proposal_windows"], new["proposal_windows"]
        if [w["path"] for w in left] != [w["path"] for w in right]:
            raise ValueError(f"{issue}: selected files differ")
        for a, b in zip(left, right):
            if (len(b["content"].encode()) > len(a["content"].encode())
                    or len(b["content"].splitlines()) > len(a["content"].splitlines())):
                raise ValueError(f"{issue}: candidate exceeded paired excerpt budget")
        exports = [(root / arm / issue / "prediction.jsonl").is_file() for arm in POLICIES]
        lines.append(f"| {issue} | {left != right} | {exports[0]} | {exports[1]} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    root = args.pilot.resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = generate(root)
    (root / "localization.md").write_text(result)
    print(result, end="")


if __name__ == "__main__":
    main()
