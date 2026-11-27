import json
from pathlib import Path

import pytest

from patchscope.proposal_contract import (
    ProposalContractError, inspect_proposal_text, validate_proposal,
)

ROOT = Path(__file__).resolve().parents[1] / "fixtures/mini_repo"


def test_proposal_response_structure_diagnostic():
    assert inspect_proposal_text("not json")["code"] == "patch_json_invalid_or_missing"
    assert inspect_proposal_text('{"path": "calculator.py"}')["code"] == "patch_fields_invalid"
    assert inspect_proposal_text('{"path": "calculator.py", "old": 3, "new": "x"}')["code"] == "patch_field_types_invalid"
    assert inspect_proposal_text('{"path": "calculator.py", "old": "x", "new": "x"}')["code"] == "patch_edit_empty_or_unchanged"
    assert inspect_proposal_text(json.dumps({"path": "calculator.py", "old": "a", "new": "b"}))["code"] == "structure_valid"


def test_strict_proposal_validation_is_bounded_to_observed_code():
    observed = {"calculator.py": (ROOT / "calculator.py").read_text()}
    candidate = {"path": "calculator.py", "old": "return sum(values) // len(values)", "new": "return sum(values) / len(values)"}
    assert validate_proposal(candidate, observed, ROOT) == candidate
    with pytest.raises(ProposalContractError, match="patch_path_not_observed_or_disallowed"):
        validate_proposal({**candidate, "path": "billing.py"}, observed, ROOT)
    with pytest.raises(ProposalContractError, match="patch_old_not_unique_in_observed"):
        validate_proposal({**candidate, "old": "missing text"}, observed, ROOT)
    with pytest.raises(ProposalContractError, match="patch_fields_invalid"):
        validate_proposal({"path": "calculator.py"}, observed, ROOT)
