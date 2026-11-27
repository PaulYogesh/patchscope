import pytest
from pathlib import Path

from patchscope.tools import list_source_files, read_source_file


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"


def test_file_listing():
    files = list_source_files(REPO)

    assert "calculator.py" in files
    assert "statistics.py" in files
    assert "test_calculator.py" not in files


def test_read_source():
    result = read_source_file(REPO, "calculator.py")

    assert "def average" in result["content"]
    assert "return sum(values) // len(values)" in result["content"]
    assert result["truncated"] is False


@pytest.mark.parametrize(
    "path",
    [
        "../README.md",
        "test_calculator.py",
    ],
)
def test_reject_unapproved_files(path):
    with pytest.raises(ValueError):
        read_source_file(REPO, path)


def test_read_does_not_modify_source():
    source = REPO / "calculator.py"
    before = source.read_bytes()

    read_source_file(REPO, "calculator.py")

    assert source.read_bytes() == before
