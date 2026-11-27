"""Run a new proposal-only, frozen-exploration comparison using v0.3 native records."""
from __future__ import annotations

import argparse
import json

from patchscope.experiment import PROJECT_ROOT, build_schedule, load_manifest
from patchscope.frozen_replay import REPLAY_ID, SOURCE_ID, SOURCE_MANIFEST, prepare_frozen, propose_frozen
from patchscope.provenance import capture_provenance
from patchscope.source_map import POLICIES
from scripts.run_experiment import save_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--task")
    parser.add_argument("--policy", choices=POLICIES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-trusted-execution", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_manifest(PROJECT_ROOT / SOURCE_MANIFEST)
    if manifest["experiment_id"] != SOURCE_ID:
        parser.error("Source manifest has an unexpected experiment ID")
    tasks = {t["task_id"]: t for t in manifest["tasks"]}
    schedule = [x for x in build_schedule(manifest) if x["condition"] == "native" and
                (args.task is None or x["task_id"] == args.task)]
    if not schedule:
        parser.error("Unknown task or no native source episode")
    output = PROJECT_ROOT / "runs" / REPLAY_ID
    pending = []
    for item in schedule:
        record_path = PROJECT_ROOT / "runs" / SOURCE_ID / (
            f"{item['task_id']}__native__r{item['repetition']:02d}.json")
        if not record_path.exists():
            parser.error(f"Missing archived source record: {record_path}")
        source_bytes = record_path.read_bytes()
        source_record = json.loads(source_bytes)
        if source_record.get("provenance", {}).get("generation", {}).get("seed") != item["model_seed"]:
            parser.error(f"Archived model seed mismatch: {item['task_id']}")
        if source_record.get("provenance", {}).get("generation", {}).get("model") != args.model:
            parser.error(f"Archived model mismatch: {item['task_id']}")
        # Validate snapshots before the model is called, even in dry-run.
        prepare_frozen(PROJECT_ROOT, source_record, tasks[item["task_id"]])
        for policy in (p for p in POLICIES if args.policy is None or p == args.policy):
            path = output / f"{item['task_id']}__{policy}__r{item['repetition']:02d}.json"
            if path.exists() and args.resume:
                print("SKIP completed:", path.name)
                continue
            if path.exists():
                parser.error(f"Existing run {path}. Use --resume; no force overwrite.")
            pending.append((policy, item, source_record, path))
    print(f"Frozen proposal protocol: {REPLAY_ID}; {len(pending)} pending runs; model={args.model}")
    if args.dry_run:
        for policy, item, source, _ in pending:
            print(f"{item['task_id']}  policy={policy}  frozen_source={source['run_id']}")
        return 0
    if not pending:
        return 0
    from patchscope.llm import get_config
    from openai import OpenAI
    config = get_config()
    client = OpenAI(base_url=config["base_url"], api_key=config["api_key"],
                    timeout=180, max_retries=0)
    provenance = capture_provenance(PROJECT_ROOT, manifest, args.model, config["base_url"])
    for policy, item, source, destination in pending:
        if source.get("provenance", {}).get("ollama", {}).get("digest") != provenance["ollama"].get("digest"):
            raise ValueError("Model digest does not match archived source run; refusing replay")
        print(f"REPLAY {item['task_id']} / {policy}")
        record = propose_frozen(
            client=client, model=args.model, policy=policy, task=tasks[item["task_id"]],
            source_record=source, source_manifest=manifest, root=PROJECT_ROOT,
            provenance=provenance, allow_trusted_execution=args.allow_trusted_execution)
        save_record(destination, record)
        print(f"   {record['outcome']['status']}  {record['usage']['total_tokens']} proposal tokens")
    print("Frozen replay records:", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
