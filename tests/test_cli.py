import json

import pytest

from scripts.run_experiment import main, select_runs, save_record
from patchscope.experiment import load_manifest, build_schedule, PROJECT_ROOT


def test_dry_run_does_not_require_ollama(capsys):
    result = main(["--dry-run", "--task", "mini-average-001", "--condition", "oracle", "--repetition", "0"])
    assert result == 0
    assert "1 runs" in capsys.readouterr().out


def test_all_forty_eight_scheduled(capsys):
    assert main(["--dry-run"]) == 0
    assert "Selected: 48 runs" in capsys.readouterr().out


def test_save_resume_and_force_contract(tmp_path):
    file = tmp_path / "a.json"
    save_record(file, {"hello": 1})
    with pytest.raises(FileExistsError):
        save_record(file, {"hello": 2})
    assert json.loads(file.read_text()) == {"hello": 1}
    save_record(file, {"hello": 3}, overwrite=True)
    assert json.loads(file.read_text()) == {"hello": 3}


def test_selection_filters():
    schedule = build_schedule(load_manifest(PROJECT_ROOT / "experiments" / "pilot_v02.json"))
    selected = select_runs(schedule, condition="placebo", repetition=1)
    assert len(selected) == 4 and all(item["condition"] == "placebo" for item in selected)
