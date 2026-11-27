from patchscope.static_review import review_python_edit


def test_rejects_syntax_error():
    result = review_python_edit("x = 1\n", "if:\n")
    assert result["passed"] is False
    assert result["code"] == "python_syntax_invalid"


def test_rejects_statement_that_parses_but_cannot_compile():
    result = review_python_edit("x = 1\n", "return 1\n")
    assert result["code"] == "python_syntax_invalid"
    assert result["line"] == 1


def test_rejects_removed_module_binding_that_is_still_used():
    original = "import logging\nlogger = logging.getLogger(__name__)\nlogger.info('ready')\n"
    changed = "import logging\n# logger removed\nlogger.info('ready')\n"
    result = review_python_edit(original, changed)
    assert result["passed"] is False
    assert result["removed_referenced_bindings"] == ["logger"]


def test_allows_binding_rename_when_references_are_updated():
    original = "value = 1\nprint(value)\n"
    changed = "answer = 1\nprint(answer)\n"
    assert review_python_edit(original, changed)["passed"] is True
