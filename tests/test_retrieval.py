from pathlib import Path

from patchscope.metrics import recall_at_k
from patchscope.retrieval import discover_files, search_repository


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"
ISSUE = REPO / "issue.md"


def test_bm25_retrieves_buggy_file():
    query = ISSUE.read_text(encoding="utf-8")

    results = search_repository(REPO, query, top_k=4)
    retrieved_paths = [result["path"] for result in results]

    assert len(results) == 4
    assert retrieved_paths[0] == "calculator.py"

    relevant_paths = {"calculator.py"}

    assert recall_at_k(
        retrieved_paths, relevant_paths, k=1
    ) == 1.0

    assert recall_at_k(
        retrieved_paths, relevant_paths, k=4
    ) == 1.0


def test_search_does_not_index_tests():
    paths = discover_files(REPO)

    names = {path.name for path in paths}

    assert "test_calculator.py" not in names
    assert len(paths) == 4


def test_search_does_not_modify_source():
    source = REPO / "calculator.py"
    before = source.read_text(encoding="utf-8")

    query = ISSUE.read_text(encoding="utf-8")
    search_repository(REPO, query)

    after = source.read_text(encoding="utf-8")

    assert before == after
