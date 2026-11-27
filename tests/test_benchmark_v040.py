"""New v0.4 benchmark fixtures: parity, baseline failure, oracle repair and decoy nonrepair."""
from __future__ import annotations

from pathlib import Path
import ast

import pytest

from patchscope.experiment import load_manifest, build_schedule
from patchscope.content_counterfactual import validate_content_variants
from patchscope.repair import temporary_repo, apply_exact_edit, run_pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("benchmark-clean-v040", "benchmark-neutral-v040", "benchmark-decoy-v040")
REFERENCES = {'tiered-billing-005': ('tax_math.py', 'return round(net * (1 + percent), 2)', 'return round(net * (1 + percent / 100), 2)', 'tax_compat.py'), 'backoff-ceiling-006': ('backoff.py', 'return max(ceiling, base * (2 ** attempt))', 'return min(ceiling, base * (2 ** attempt))', 'retry_compat.py'), 'stock-exact-007': ('allocation.py', 'return requested < available', 'return requested <= available', 'stock_compat.py'), 'one-index-pages-008': ('pagination.py', 'return page * size', 'return (page - 1) * size', 'pagination_compat.py'), 'owner-access-009': ('policy.py', 'return role == "admin" and user_id == owner_id', 'return role == "admin" or user_id == owner_id', 'policy_compat.py'), 'sensor-offset-010': ('calibration.py', 'return round(raw - offset, 2)', 'return round(raw + offset, 2)', 'calibration_compat.py'), 'window-inclusive-011': ('intervals.py', 'return start < sample < stop', 'return start <= sample < stop', 'window_compat.py'), 'f1-harmonic-012': ('scores.py', 'return (precision + recall) / 2', 'return 2 * precision * recall / (precision + recall)', 'scores_compat.py')}


def manifests():
    return [load_manifest(ROOT / "experiments" / (name + ".json")) for name in NAMES]


def test_eight_new_independent_tasks_and_parity():
    clean, neutral, decoy = manifests()
    rows = validate_content_variants(clean, neutral, decoy, ROOT)
    assert len(rows) == 8
    assert len({row["task_id"] for row in rows}) == 8
    assert all(row["neutral_bytes"] == row["decoy_bytes"] for row in rows)


def test_matched_generator_seeds():
    triples = []
    for manifest in manifests():
        triples.append({r["task_id"]: r["model_seed"] for r in build_schedule(manifest) if r["condition"] == "native"})
    assert triples[0] == triples[1] == triples[2]


@pytest.mark.parametrize("variant", ["clean", "neutral", "decoy"])
@pytest.mark.parametrize("task_id", sorted(REFERENCES))
def test_baseline_fail_and_reference_repair(variant,task_id):
    repo=ROOT / "fixtures" / "benchmark_v040" / variant / task_id
    with temporary_repo(repo) as work:
        assert not run_pytest(work)["passed"], (variant,task_id)
        target, old, new, _ = REFERENCES[task_id]
        apply_exact_edit(work,target,old,new)
        assert run_pytest(work)["passed"], (variant,task_id)


@pytest.mark.parametrize("task_id", sorted(REFERENCES))
def test_decoy_edit_alone_cannot_repair(task_id):
    repo=ROOT / "fixtures" / "benchmark_v040" / "decoy" / task_id
    target,old,new,decoy=REFERENCES[task_id]
    with temporary_repo(repo) as work:
        assert not run_pytest(work)["passed"]
        apply_exact_edit(work,decoy,old,new)
        assert not run_pytest(work)["passed"]


@pytest.mark.parametrize("task_id", sorted(REFERENCES))
def test_real_service_never_imports_decoy(task_id):
    repo=ROOT / "fixtures" / "benchmark_v040" / "decoy" / task_id
    extra=REFERENCES[task_id][-1][:-3]
    for path in repo.glob("*.py"):
        if path.name.startswith("test_") or path.stem == extra:
            continue
        ast_tree=ast.parse(path.read_text(encoding="utf-8"))
        imported=[node.module for node in ast.walk(ast_tree) if isinstance(node,ast.ImportFrom)]
        imported += [alias.name for node in ast.walk(ast_tree) if isinstance(node,ast.Import) for alias in node.names]
        assert extra not in imported, (task_id,path)
