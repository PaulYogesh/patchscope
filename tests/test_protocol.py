from types import SimpleNamespace as NS

import pytest

from patchscope.protocol import (
    ToolProtocolError, TOOL_MODE_NATIVE_REQUIRED, TOOL_MODE_FALLBACK_ALLOWED,
    decode_message, parse_json_dict, validate_action,
)


def native(name="read_file", args='{"path":"calculator.py"}', id="call-001"):
    return NS(content=None, tool_calls=[NS(id=id, type="function", function=NS(name=name, arguments=args))])


def text_request():
    return NS(content='{"name":"read_file","arguments":{"path":"calculator.py"}}', tool_calls=[])


def test_native_accepted():
    actions, final = decode_message(native(), mode=TOOL_MODE_NATIVE_REQUIRED)
    assert actions[0].call_id == "call-001"
    assert actions[0].mode == "native"
    assert final is None


def test_invalid_native_name_rejected():
    with pytest.raises(ToolProtocolError):
        decode_message(native(name="shell"), mode=TOOL_MODE_NATIVE_REQUIRED)


def test_malformed_arguments_rejected():
    with pytest.raises(ToolProtocolError):
        decode_message(native(args='{"path": 4}'), mode=TOOL_MODE_NATIVE_REQUIRED)


def test_missing_native_call_id_rejected():
    with pytest.raises(ToolProtocolError):
        decode_message(native(id=None), mode=TOOL_MODE_NATIVE_REQUIRED)


def test_textual_tool_request_rejected_in_primary():
    with pytest.raises(ToolProtocolError, match="tool_protocol_violation"):
        decode_message(text_request(), mode=TOOL_MODE_NATIVE_REQUIRED)


def test_textual_tool_request_allowed_in_compat():
    actions, final = decode_message(text_request(), mode=TOOL_MODE_FALLBACK_ALLOWED)
    assert actions[0].mode == "validated_text_fallback"
    assert actions[0].call_id is None
    assert final is None


def test_plain_response_is_not_tool_request():
    actions, final = decode_message(NS(content="Enough evidence", tool_calls=[]), mode=TOOL_MODE_NATIVE_REQUIRED)
    assert not actions and final == "Enough evidence"


def test_fenced_json_proposal_parses():
    assert parse_json_dict('```json\n{"x":3}\n```') == {"x": 3}


def test_extra_args_forbidden():
    with pytest.raises(ToolProtocolError):
        validate_action("read_file", {"path": "a.py", "mode": "raw"})
