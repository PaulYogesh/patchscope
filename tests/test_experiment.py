from pathlib import Path

import pytest

from patchscope.experiment import load_manifest, build_schedule, manifest_sha256, stable_seed

ROOT = Path(__file__).resolve().parents[1]


def load():
    return load_manifest(ROOT / "experiments" / "pilot_v02.json")


def test_manifest_validates_and_hashes():
    data = load()
    assert len(manifest_sha256(data)) == 64
    assert len(data["tasks"]) == 4


def test_schedule_length_and_randomization_repeatable():
    data = load()
    schedule = build_schedule(data)
    assert len(schedule) == 48
    assert schedule == build_schedule(data)


def test_all_conditions_share_block_seed():
    schedule = build_schedule(load())
    for rep in (0, 1):
        group = [item for item in schedule if item["repetition"] == rep]
        for task_id in {row["task_id"] for row in group}:
            block = [row for row in group if row["task_id"] == task_id]
            assert len(set(row["model_seed"] for row in block)) == 1
            assert len(set(row["condition"] for row in block)) == 4
            assert len(set(row["block_seed"] for row in block)) == 1


def test_seed_is_stable_across_processes():
    assert stable_seed(42, "mini-average-001", 1) == 1403286220


def test_oracle_cannot_share_placebo_files(tmp_path):
    data = load()
    data["tasks"][0]["placebo_pool"].append("calculator.py")
    path = tmp_path / "bad.json"
    import json
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        load_manifest(path)


def test_escapes_project_rejected(tmp_path):
    data = load()
    data["tasks"][0]["repo_path"] = "../../etc"
    path = tmp_path / "bad.json"
    import json
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


def test_five_arm_manifest_20_runs_and_equal_block_seeds():
    data = load_manifest(ROOT / "experiments" / "interference_smoke_v030.json")
    schedule = build_schedule(data)
    assert len(schedule) == 20
    for task in data["tasks"]:
        block = [r for r in schedule if r["task_id"] == task["task_id"]]
        assert len(block) == 5
        assert len({r["model_seed"] for r in block}) == 1
        assert {r["condition"] for r in block} == set(data["conditions"])


def test_five_arm_manifest_rejects_wrong_locus_that_is_actually_oracle(tmp_path):
    import json
    data = load_manifest(ROOT / "experiments" / "interference_smoke_v030.json")
    data["tasks"][0]["misleading_pool"] = ["calculator.py"]
    location = tmp_path / "wrong.json"
    location.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        load_manifest(location)


def test_optional_misleading_pool_is_not_required_for_legacy_manifests():
    assert load_manifest(ROOT / "experiments" / "pilot_v02.json")["conditions"] == ["native", "bm25", "placebo", "oracle"]
