"""Audit matched frozen-exploration proposal runs (no LLM calls)."""
from __future__ import annotations

import json

from patchscope.experiment import PROJECT_ROOT
from patchscope.frozen_replay import REPLAY_ID, compare_frozen, render_frozen
from patchscope.source_map import POLICIES


def main():
    folder = PROJECT_ROOT / "runs" / REPLAY_ID
    rows = {policy: {} for policy in POLICIES}
    for p in sorted(folder.glob("*.json")):
        record = json.loads(p.read_text(encoding="utf-8"))
        policy = record.get("policy")
        if policy not in rows:
            raise ValueError(f"Invalid replay record policy: {p}")
        key = (record["task_id"], record["repetition"])
        if key in rows[policy]:
            raise ValueError("duplicate_frozen_replay")
        rows[policy][key] = record
    report = compare_frozen(rows)
    target = PROJECT_ROOT / "reports" / "frozen-proposal-v051"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    target.with_suffix(".md").write_text(render_frozen(report), encoding="utf-8")
    print(f"Wrote {target}.md and .json ({report['n_matched']} matched episodes)")


if __name__ == "__main__":
    main()
