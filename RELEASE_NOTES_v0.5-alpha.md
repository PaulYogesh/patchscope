# PatchScope v0.5-alpha — Proposal-Stage Static Reference Evidence

**Engineering experiment, not a validated repair improvement.**

Adds an optional bounded static source reference map, made only from agent-readable non-test Python modules, injected at patch-proposal stage. Existing manifests default to `evidence_policy=off`. `inventory` provides a file-inventory control; `imports` adds importer-to-imported relationships. Both are new interventions and use separate experiment identifiers.

New:
- `patchscope/source_map.py` — deterministic AST import relationships, no imports executed or oracle leakage.
- Optional validated `evidence_policy` and `source_map_char_budget` manifest fields.
- Proposal-stage injection, event and record metadata, same exploration stage and standard tool surface.
- Four development-task and eight benchmark-regression-task manifests, with original deterministic seeds.
- Offline three-arm comparator verifying task/seed/model/budgets and logged exploration parity.
- Source map, legacy-compatibility, client-call stage-isolation, and comparison tests.

Limitations: static source imports are not call graphs or runtime proof. Context is not token-matched between the two map conditions. The original failure tasks may have no useful static edges. Any outcome is exploratory, not generalizable. Live Ollama experiments must run on the user's computer.
