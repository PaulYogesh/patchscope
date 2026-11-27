from pathlib import Path

import pytest

from patchscope.context import build_context_seed


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"
ISSUE = REPO / "issue.md"


def test_seed_contains_relevant_source():
    issue = ISSUE.read_text(encoding="utf-8")

    result = build_context_seed(
        REPO,
        issue,
        top_k=1,
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["path"] == "calculator.py"

    assert "def average" in result["seed_text"]
    assert "sum(values) // len(values)" in result["seed_text"]

    assert result["seed_chars"] == len(result["seed_text"])
    assert result["retrieval_ms"] >= 0


def test_seed_does_not_include_tests():
    issue = ISSUE.read_text(encoding="utf-8")
    result = build_context_seed(REPO, issue)

    assert "test_fractional_average" not in result["seed_text"]


def test_unmatched_query_produces_empty_seed():
    result = build_context_seed(
        REPO,
        "zzzxylophoneunmatchedterm",
    )

    assert result["sources"] == []
    assert result["seed_text"] == ""


def test_rejects_invalid_budget():
    with pytest.raises(ValueError):
        build_context_seed(REPO, "bug", top_k=0)
