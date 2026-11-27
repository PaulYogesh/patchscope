"""Self-contained safety regressions for the v0.9 line-range contract."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from patchscope.proposal_contract import (
    ProposalContractError,
    materialize_line_edit,
    observed_span,
    validate_line_proposal,
)
from patchscope.repair import apply_line_edit


def _repo(tmp_path: Path) -> Path:
    source = (
        "def first():\n"
        "    return 1\n"
        "\n"
        "def second():\n"
        "    return 1\n"
    )
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    return tmp_path


def test_duplicate_text_is_safely_disambiguated_by_observed_line(tmp_path):
    repo = _repo(tmp_path)
    shown = "def second():\n    return 1\n"
    proposal = validate_line_proposal(
        {"path": "module.py", "start_line": 5, "end_line": 5,
         "replacement": "    return 2\n"},
        [observed_span("module.py", 4, shown)],
        repo,
    )
    assert proposal["expected_sha256"] == hashlib.sha256(
        b"    return 1\n").hexdigest()
    apply_line_edit(repo, proposal)
    assert (repo / "module.py").read_text(encoding="utf-8") == (
        "def first():\n    return 1\n\ndef second():\n    return 2\n"
    )


def test_unobserved_line_range_is_rejected(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ProposalContractError, match="patch_range_not_fully_observed"):
        validate_line_proposal(
            {"path": "module.py", "start_line": 2, "end_line": 2,
             "replacement": "    return 2\n"},
            [observed_span("module.py", 4, "def second():\n    return 1\n")],
            repo,
        )


def test_line_edit_preserves_crlf_while_hashing_the_observed_text(tmp_path):
    source = tmp_path / "module.py"
    source.write_bytes(b"value = 1\r\nprint(value)\r\n")
    proposal = validate_line_proposal(
        {"path": "module.py", "start_line": 1, "end_line": 1, "replacement": "value = 2\n"},
        [observed_span("module.py", 1, "value = 1\n")],
        tmp_path,
    )
    assert proposal["expected_sha256"] == hashlib.sha256(b"value = 1\n").hexdigest()
    apply_line_edit(tmp_path, proposal)
    assert source.read_bytes() == b"value = 2\r\nprint(value)\r\n"


def test_stale_source_hash_is_rejected_at_materialization_and_apply(tmp_path):
    repo = _repo(tmp_path)
    proposal = validate_line_proposal(
        {"path": "module.py", "start_line": 2, "end_line": 2,
         "replacement": "    return 2\n"},
        [observed_span("module.py", 1, "def first():\n    return 1\n")],
        repo,
    )
    stale = (repo / "module.py").read_text().replace("return 1", "return 9", 1)
    with pytest.raises(ProposalContractError, match="patch_source_hash_mismatch"):
        materialize_line_edit(proposal, stale)
    (repo / "module.py").write_text(stale)
    with pytest.raises(ValueError, match="source hash mismatch"):
        apply_line_edit(repo, proposal)


@pytest.mark.parametrize(
    "candidate,code",
    [
        ({"path": "module.py", "start_line": 0, "end_line": 1,
          "replacement": "x"}, "patch_line_range_invalid"),
        ({"path": "module.py", "start_line": True, "end_line": 1,
          "replacement": "x"}, "patch_field_types_invalid"),
        ({"path": "module.py", "start_line": 1, "end_line": 1,
          "replacement": "def first():\n", "extra": 1}, "patch_fields_invalid"),
    ],
)
def test_invalid_contract_shapes_are_rejected(tmp_path, candidate, code):
    repo = _repo(tmp_path)
    with pytest.raises(ProposalContractError, match=code):
        validate_line_proposal(
            candidate,
            [observed_span("module.py", 1, (repo / "module.py").read_text())],
            repo,
        )
