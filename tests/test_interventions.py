import random
from pathlib import Path

import pytest

from patchscope.interventions import build_intervention, CONDITIONS

REPO = Path(__file__).resolve().parents[1] / "fixtures" / "mini_repo"
ISSUE = (REPO / "issue.md").read_text(encoding="utf-8")


def make(condition, *, seed=7, placebo_pool=None, misleading_pool=None, char_budget=1600):
    repo = (REPO.parent / "interference_mini_repo") if condition == "misleading" else REPO
    return build_intervention(
        condition, repo_path=repo, issue_text=ISSUE,
        oracle_paths=["calculator.py"],
        placebo_pool=placebo_pool if placebo_pool is not None else ["billing.py", "formatting.py", "statistics.py"],
        misleading_pool=misleading_pool if misleading_pool is not None else ["average_utils.py"],
        rng=random.Random(seed), top_k=1, char_budget=char_budget,
    )


def test_conditions_complete():
    assert set(CONDITIONS) == {"native", "bm25", "placebo", "oracle", "misleading"}


def test_native_has_no_seed():
    result = make("native")
    assert result["seed_chars"] == 0 and not result["sources"]


def test_bm25_preserves_buggy_source():
    result = make("bm25")
    assert [s["path"] for s in result["sources"]] == ["calculator.py"]
    assert "sum(values) // len(values)" in result["seed_text"]


def test_oracle_includes_only_gold():
    result = make("oracle")
    assert [s["path"] for s in result["sources"]] == ["calculator.py"]


def test_placebo_never_selects_oracle():
    result = make("placebo", placebo_pool=["calculator.py", "billing.py"])
    assert result["sources"][0]["path"] == "billing.py"
    assert "def average(" not in result["seed_text"]


def test_placebo_is_deterministic():
    assert make("placebo", seed=124)["seed_text"] == make("placebo", seed=124)["seed_text"]


@pytest.mark.parametrize("condition", CONDITIONS)
def test_no_tests_and_budget(condition):
    result = make(condition, char_budget=180)
    assert len(result["seed_text"]) <= 180
    assert "test_fractional_average" not in result["seed_text"]
    assert "test_calculator.py" not in result["seed_text"]


def test_rejects_leaked_test_oracle():
    with pytest.raises(ValueError):
        build_intervention(
            "oracle", repo_path=REPO, issue_text=ISSUE,
            oracle_paths=["test_calculator.py"], placebo_pool=["billing.py"],
            rng=random.Random(1), char_budget=1600,
        )


def test_invalid_candidate_path():
    with pytest.raises(ValueError):
        make("placebo", placebo_pool=["../README.md"])


def test_misleading_is_real_but_wrong_locus_code():
    result = make("misleading")
    assert [src["path"] for src in result["sources"]] == ["average_utils.py"]
    assert "def average(values)" in result["seed_text"]
    assert "calculator.py" not in result["seed_text"]
    assert "misleading_length_gap" in result
    assert result["sources"][0]["selection"] == "misleading"


def test_misleading_rejects_oracle_as_candidate():
    with pytest.raises(ValueError, match="outside oracle"):
        make("misleading", misleading_pool=["calculator.py"])


def test_misleading_invalid_path_not_accepted():
    with pytest.raises(ValueError):
        make("misleading", misleading_pool=["../README.md"])
