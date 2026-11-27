"""Run only the native proposal pass from verified source in a saved dev episode."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from patchscope.agent import run_episode
from patchscope.proposal_windows import WINDOW_BYTE_LIMIT, read_replay_source, select_replayed_spans
from patchscope.swebench_dev import (
    DATASET, FULL_DEV_DATASET, external_manifest, load_prepared, prepare_dev_instance, save_episode_prediction,
)


def run_native_replay(source: Path, destination: Path, *, client, benchmark=DATASET, traceback_policy=False):
    source = source.expanduser().resolve()
    public = load_prepared(source)
    raw = (source / "episode.json").read_bytes()
    episode = json.loads(raw)
    provenance = episode["provenance"]
    issue_hash = hashlib.sha256(public["problem_statement"].encode()).hexdigest()
    if (episode["task_id"] != public["instance_id"] or episode["condition"] != "native"
            or benchmark not in {DATASET, FULL_DEV_DATASET} or provenance["benchmark"] != benchmark or provenance["split"] != "dev"
            or provenance["base_commit"] != public["base_commit"]
            or provenance["public_issue_sha256"] != issue_hash or episode.get("editor_comparator")
            or episode.get("proposal_windows") is not None or episode.get("tool_call_recovery")):
        raise ValueError("Saved exploration does not match this native development workspace")
    generation = provenance["generation"]
    model = generation["model"]
    windows = select_replayed_spans(source / "repo", episode)
    if traceback_policy:
        from patchscope.traceback_windows import reposition, traceback_frames
        issue = public["problem_statement"]
        frames = traceback_frames(issue)
        windows = [
            reposition(w, read_replay_source(source / "repo", w["path"]), issue, frames)[0]
            for w in windows
        ]
    workspace = prepare_dev_instance(public, destination, clone_source=source / "repo")
    manifest, item = external_manifest(
        public, model=model, matched_source=True,
        proposal_reasoning_effort=generation.get("proposal_reasoning_effort"),
        behavioral_proposal=generation.get("behavioral_proposal", False),
    )
    if benchmark == FULL_DEV_DATASET:
        manifest["experiment_id"] = manifest["experiment_id"].replace("swebench_lite_", "swebench_full_", 1)
    manifest["experiment_id"] += "_traceback_windows" if traceback_policy else "_replayed_windows"
    manifest["model"]["temperature"] = generation.get("temperature", 0)
    item["model_seed"] = generation["seed"]
    budgets = manifest["budgets"]
    budgets.pop("proposal_reserve_tokens", None)
    budgets.update(max_steps=0, max_model_calls=2, max_tool_calls=0,
                   max_patch_completion_tokens_per_call=2400,
                   proposal_source_byte_limit=WINDOW_BYTE_LIMIT)
    saved = run_episode(
        item=item, manifest=manifest, root=workspace, client=client, model=model,
        provenance={**provenance, "window_policy": "traceback_v1" if traceback_policy else "saved_reads_v1",
                    "exploration_episode_sha256": hashlib.sha256(raw).hexdigest()},
        replay_spans=windows,
    )
    return saved, save_episode_prediction(workspace, saved, model=model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    from openai import OpenAI
    from patchscope.llm import get_config

    config = get_config()
    client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=180, max_retries=0)
    try:
        record, prediction = run_native_replay(args.source, args.workspace_root, client=client)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(f"Native replay status: {record['outcome']['status']}")
    if record.get("error"):
        print(f"Native replay error: {record['error']}")
    print(f"Shared windows: {len(record['proposal_windows'])}, tool calls: {record['usage']['tool_calls']}")
    print(f"Prediction: {prediction or 'NOT EXPORTED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
