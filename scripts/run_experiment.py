"""Batch runner for frozen, paired PatchScope context-intervention experiments."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from patchscope.agent import run_episode
from patchscope.interventions import CONDITIONS
from patchscope.experiment import (
    PROJECT_ROOT, build_schedule, load_manifest, manifest_sha256, run_id,
)
from patchscope.provenance import capture_provenance
from patchscope.protocol import TOOL_MODE_NATIVE_REQUIRED, TOOL_MODE_FALLBACK_ALLOWED


def select_runs(schedule, *, task=None, condition=None, repetition=None):
    return [item for item in schedule
            if (task is None or item["task_id"] == task)
            and (condition is None or item["condition"] == condition)
            and (repetition is None or item["repetition"] == repetition)]


def save_record(path: Path, record: dict, *, overwrite=False):
    """Atomic write, do not overwrite existing records by accident."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Run record already exists: {path}")
    temporary = path.with_name(path.name + ".pending")
    if temporary.exists():
        raise FileExistsError(f"Unresolved pending record: {temporary}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    if path.exists() and not overwrite:
        temporary.unlink()
        raise FileExistsError(str(path))
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "experiments" / "pilot_v02.json")
    parser.add_argument("--model", default=None)
    parser.add_argument("--task")
    parser.add_argument("--condition", choices=CONDITIONS)
    parser.add_argument("--repetition", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-trusted-execution", action="store_true",
                        help="Opt in to pytest on model-edited trusted fixture copies; NOT a sandbox")
    parser.add_argument("--allow-text-fallback", action="store_true",
                        help="Compatibility lane only: exclude from strict-native primary comparison")
    args = parser.parse_args(argv)
    if args.resume and args.force:
        parser.error("--resume and --force cannot be combined")

    manifest = load_manifest(args.manifest)
    schedule = select_runs(build_schedule(manifest), task=args.task,
                           condition=args.condition, repetition=args.repetition)
    if not schedule:
        parser.error("Selection contains no scheduled runs")
    model = args.model or manifest["model"]["primary"]
    print(f"Experiment: {manifest['experiment_id']} (manifest sha256 {manifest_sha256(manifest)[:16]}...)")
    print(f"Selected: {len(schedule)} runs; model: {model}")
    if args.dry_run:
        for item in schedule:
            print(f"{run_id(item)}  seed={item['model_seed']}  block={item['block_seed']}")
        return 0

    if not args.allow_trusted_execution:
        print("Verification opt-in not provided: patches will NOT be executed; "
              "outcomes will be marked unverified.")
    else:
        print("WARNING: Running model-generated edits under pytest on this host. "
              "Temporary directories are NOT security sandboxes. "
              "Use only your own trusted, small fixtures.")

    from patchscope.llm import get_config
    config = get_config()
    policy = TOOL_MODE_FALLBACK_ALLOWED if args.allow_text_fallback else TOOL_MODE_NATIVE_REQUIRED
    output_dir = PROJECT_ROOT / "runs" / manifest["experiment_id"]
    pending = []
    for item in schedule:
        filename = output_dir / (run_id(item) + ".json")
        if filename.exists() and args.resume:
            print("SKIP completed:", filename.name)
        elif filename.exists() and not args.force:
            parser.error(f"Existing run {filename}; use --resume or --force")
        else:
            pending.append((item, filename))
    if not pending:
        return 0
    from openai import OpenAI
    client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=180,
                    max_retries=0)
    provenance = capture_provenance(PROJECT_ROOT, manifest, model, config["base_url"])
    n_resolved = 0
    for idx, (item, path) in enumerate(pending, start=1):
        print(f"[{idx}/{len(pending)}] {run_id(item)}")
        try:
            record = run_episode(
                item=item, manifest=manifest, root=PROJECT_ROOT, client=client,
                model=model, provenance=provenance,
                allow_trusted_execution=args.allow_trusted_execution,
                tool_mode=policy,
            )
        except Exception as exc:
            # Prevent a single exception from silently corrupting a batch.
            print(f"HALT on unrecorded fatal error: {exc}")
            raise
        save_record(path, record, overwrite=args.force)
        print("  ", record["outcome"]["status"], record["usage"]["total_tokens"], "tokens")
        n_resolved += int(record["outcome"]["repair_verified"])
    print(f"Finished {len(pending)} runs; {n_resolved} verified repairs. Logs: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
