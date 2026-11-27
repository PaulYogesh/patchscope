"""Diagnose already-recorded PatchScope failures without model calls or pytest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchscope.experiment import PROJECT_ROOT, load_manifest
from patchscope.failure_triage import render_triage, triage_records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    run_dir = PROJECT_ROOT / "runs" / manifest["experiment_id"]
    paths = sorted(run_dir.glob("*.json"))
    if not paths:
        parser.error(f"No run records under {run_dir}")
    records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if any(r.get("schema_version") != 2 for r in records):
        parser.error("Only v0.2 schema_version=2 records can be triaged")
    summary = triage_records(records, manifest)
    out = PROJECT_ROOT / "reports" / manifest["experiment_id"]
    out.parent.mkdir(parents=True, exist_ok=True)
    json_out = out.with_suffix(".triage.json")
    md_out = out.with_suffix(".triage.md")
    json_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    md_out.write_text(render_triage(summary, manifest=manifest), encoding="utf-8")
    print(f"Wrote {md_out} and {json_out} ({len(records)} runs; no model calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
