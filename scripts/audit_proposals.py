"""Audit archived model patch responses without rerunning Qwen or tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchscope.experiment import PROJECT_ROOT, load_manifest
from patchscope.proposal_audit import audit_proposals, render_proposal_audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "experiments/pilot_v02.json")
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    folder = PROJECT_ROOT / "runs" / manifest["experiment_id"]
    files = sorted(folder.glob("*.json"))
    if not files:
        parser.error(f"No JSON logs in {folder}")
    records = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    if any(r.get("experiment_id") != manifest["experiment_id"] for r in records):
        parser.error("A record has a different experiment_id")
    data = audit_proposals(records)
    stem = PROJECT_ROOT / "reports" / f"{manifest['experiment_id']}.proposals"
    stem.parent.mkdir(parents=True, exist_ok=True)
    Path(str(stem) + ".json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    Path(str(stem) + ".md").write_text(render_proposal_audit(data), encoding="utf-8")
    print(f"Wrote {stem}.md and .json ({len(records)} archived runs; no model calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
